"""Tests for long-term memory injection into generator and planner context."""

from pathlib import Path
from typing import Any

import pytest

from db.engine import DatabaseEngine
from multi_agent.executor import ToolExecutor
from repositories.memory_repository import MemoryRepository
from schemas.agent_state import AgentState
from schemas.memory import MemoryCandidate
from schemas.route import RouteResult
from schemas.tool import ToolResult
from tools.base import BaseTool
from tools.registry import ToolRegistry


class RecordingTool(BaseTool):
    name = "plan_itinerary"
    description = "plan"

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self.calls = calls

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        self.calls.append(tool_input)
        return ToolResult.ok(self.name, {"ok": True})


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'memory.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def candidate(**kwargs: Any) -> MemoryCandidate:
    values = {
        "user_id": "memory_user",
        "memory_type": "semantic",
        "category": "interests",
        "statement": "用户喜欢博物馆和历史街区",
        "evidence_text": "用户明确表示喜欢博物馆和历史街区",
        "evidence_type": "explicit_statement",
        "confidence": 0.98,
    }
    values.update(kwargs)
    return MemoryCandidate(**values)


def test_executor_injects_long_term_memory_into_generator_context(database: DatabaseEngine) -> None:
    with database.session() as session:
        MemoryRepository(session).create_item(candidate())

    calls: list[dict[str, Any]] = []
    registry = ToolRegistry()
    registry.register(RecordingTool(calls))
    retrieval = _StubMemoryRetrieval()
    with database.session() as session:
        retrieval.set_items(
            [MemoryRepository.to_retrieved(item) for item in MemoryRepository(session).list_items("memory_user")]
        )
    executor = ToolExecutor(
        registry,
        memory_retrieval=retrieval,
    )
    state = AgentState(user_id="memory_user", session_id="session_memory")

    executor.execute(
        RouteResult(intent="plan", tool_name="plan_itinerary", confidence=0.9),
        "帮我规划历史文化行程",
        state,
    )

    context = calls[0]["contextual_input"]
    assert "长期记忆：" in context
    assert "用户喜欢博物馆和历史街区" in context
    assert "类型：semantic" in context
    assert state.active_memories[0]["statement"] == "用户喜欢博物馆和历史街区"


def test_executor_respects_personalization_disabled(database: DatabaseEngine) -> None:
    from repositories.user_repository import UserRepository

    with database.session() as session:
        UserRepository(session).create("memory_user")
        UserRepository(session).update_settings("memory_user", personalization_enabled=False)

    calls: list[dict[str, Any]] = []
    registry = ToolRegistry()
    registry.register(RecordingTool(calls))
    executor = ToolExecutor(
        registry,
        memory_retrieval=_StubMemoryRetrieval(),
    )
    state = AgentState(user_id="memory_user", session_id="session_memory")

    executor.execute(
        RouteResult(intent="plan", tool_name="plan_itinerary", confidence=0.9),
        "帮我规划历史文化行程",
        state,
    )

    assert "长期记忆：" not in calls[0]["contextual_input"]
    assert state.active_memories == []


class _StubMemoryRetrieval:
    def __init__(self) -> None:
        self.items: list = []

    def set_items(self, items: list) -> None:
        self.items = items

    def retrieve(self, user_id: str, query: str, **kwargs: Any):
        return self.items
