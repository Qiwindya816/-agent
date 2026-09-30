"""Tests for the memory pipeline and FeedbackAgent memory ingestion."""

from pathlib import Path
from typing import Any

import pytest

from db.engine import DatabaseEngine
from multi_agent.nodes import FeedbackAgent
from repositories.memory_repository import MemoryRepository
from schemas.agent_state import AgentState
from schemas.user_profile import ProfileExtraction, UserProfile


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'memory.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def candidate_data(**kwargs: Any) -> dict[str, Any]:
    data = {
        "memory_type": "explicit",
        "category": "interests",
        "statement": "用户喜欢博物馆",
        "structured_value": {},
        "scope": "global",
        "polarity": "positive",
        "importance": 0.8,
        "confidence": 0.98,
        "evidence_text": "用户说：请记住我喜欢博物馆",
        "evidence_type": "explicit_statement",
    }
    data.update(kwargs)
    return data


def test_memory_pipeline_creates_explicit_memory(database: DatabaseEngine) -> None:
    from services.memory_pipeline import MemoryPipeline

    pipeline = MemoryPipeline(database)
    result = pipeline.ingest_candidates(
        [candidate_data()],
        user_id="memory_user",
        session_id="session_memory",
        trip_id="trip_memory",
    )

    assert result.created
    with database.session() as session:
        item = MemoryRepository(session).list_items("memory_user")[0]
        assert item.memory_type == "explicit"
        assert item.evidence_count == 1


def test_memory_pipeline_merges_duplicate_evidence(database: DatabaseEngine) -> None:
    from services.memory_pipeline import MemoryPipeline

    pipeline = MemoryPipeline(database)
    first = pipeline.ingest_candidates([candidate_data()], user_id="memory_user")
    second = pipeline.ingest_candidates([candidate_data()], user_id="memory_user")

    assert len(first.created) == 1
    assert len(second.merged) == 1
    with database.session() as session:
        item = MemoryRepository(session).list_items("memory_user")[0]
        assert item.evidence_count == 2


def test_memory_pipeline_defers_low_confidence_semantic_memory(database: DatabaseEngine) -> None:
    from services.memory_pipeline import MemoryPipeline

    result = MemoryPipeline(database).ingest_candidates(
        [candidate_data(memory_type="semantic", confidence=0.6, statement="用户可能喜欢慢节奏")],
        user_id="memory_user",
    )

    assert result.deferred
    assert not result.created


def test_memory_pipeline_rejects_sensitive_information(database: DatabaseEngine) -> None:
    from services.memory_pipeline import MemoryPipeline

    result = MemoryPipeline(database).ingest_candidates(
        [candidate_data(statement="用户身份证号是123456", evidence_text="身份证")],
        user_id="memory_user",
    )

    assert result.rejected


def test_feedback_agent_ingests_memory_candidates(database: DatabaseEngine) -> None:
    from services.memory_pipeline import MemoryPipeline

    def extractor(*args: Any, **kwargs: Any) -> ProfileExtraction:
        return ProfileExtraction(
            profile_updates=UserProfile(),
            memory_candidates=[candidate_data()],
        )

    agent = FeedbackAgent(extractor=extractor, memory_pipeline=MemoryPipeline(database))
    state = {
        "user_id": "feedback_memory_user",
        "session_id": "session_feedback_memory",
        "user_input": "请记住我喜欢博物馆",
        "agent_state": {
            "user_id": "feedback_memory_user",
            "session_id": "session_feedback_memory",
            "chat_history": [],
        },
        "node_trace": [],
    }

    result = agent(state)

    assert result["agent_state"]["last_memory_result"]["created"]
    with database.session() as session:
        items = MemoryRepository(session).list_items("feedback_memory_user")
        assert len(items) == 1
        assert items[0].statement == "用户喜欢博物馆"


def test_deterministic_memory_extraction_detects_explicit_instruction() -> None:
    from tools.profile_tool import extract_memory_candidates_from_text

    candidates = extract_memory_candidates_from_text("请记住我喜欢博物馆")

    assert candidates[0]["memory_type"] == "explicit"
    assert candidates[0]["confidence"] == 0.98


def test_user_can_disable_long_term_memory(database: DatabaseEngine) -> None:
    from repositories.user_repository import UserRepository
    from services.memory_pipeline import MemoryPipeline

    with database.session() as session:
        UserRepository(session).create("memory_user")
        UserRepository(session).update_settings("memory_user", long_term_memory_enabled=False)

    result = MemoryPipeline(database).ingest_candidates(
        [candidate_data()],
        user_id="memory_user",
    )

    assert result.rejected == ["long_term_memory_disabled"]
    with database.session() as session:
        assert MemoryRepository(session).list_items("memory_user") == []


def test_router_prompt_includes_active_procedural_memory() -> None:
    from prompts.router_prompt import build_router_prompt

    state = AgentState(user_id="user_a", session_id="session_a")
    state.active_memories = [
        {
            "memory_type": "procedural",
            "statement": "用户希望每次规划行程时先给三个候选目的地",
            "confidence": 0.98,
        }
    ]

    prompt = build_router_prompt("帮我规划旅行", state)

    assert "long_term_memory" in prompt
    assert "用户希望每次规划行程时先给三个候选目的地" in prompt
    assert "当前用户输入优先级最高" in prompt
