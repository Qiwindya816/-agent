"""Tests for long-term memory repository, write policy, retrieval, and conflict resolution."""

from pathlib import Path

import pytest

from db.engine import DatabaseEngine
from repositories.memory_repository import MemoryRepository
from schemas.memory import MemoryCandidate
from services.memory_conflict_resolver import MemoryConflictResolver
from services.memory_retrieval import MemoryRetrievalService
from services.memory_write_policy import MemoryWritePolicy


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'memory.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def candidate(**kwargs) -> MemoryCandidate:
    values = {
        "user_id": "user_a",
        "memory_type": "semantic",
        "category": "interests",
        "statement": "用户喜欢博物馆",
        "evidence_text": "用户说他喜欢博物馆",
        "evidence_type": "explicit_statement",
        "confidence": 0.98,
    }
    values.update(kwargs)
    return MemoryCandidate(**values)


def test_memory_repository_creates_item_and_evidence(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = MemoryRepository(session)
        item = repository.create_item(candidate())

        assert item.memory_type == "semantic"
        assert item.evidence_count == 1
        assert repository.get_item("user_a", item.memory_id) is not None
        assert repository.get_item("user_b", item.memory_id) is None


def test_memory_repository_updates_and_deletes_with_user_isolation(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = MemoryRepository(session)
        item = repository.create_item(candidate())

        assert repository.update_statement("user_a", item.memory_id, "用户非常喜欢博物馆") is not None
        assert repository.get_item("user_a", item.memory_id).statement == "用户非常喜欢博物馆"
        assert repository.update_statement("user_b", item.memory_id, "不应该修改") is None
        assert repository.delete_item("user_a", item.memory_id) is True


def test_write_policy_creates_explicit_and_rejects_low_confidence(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = MemoryRepository(session)
        policy = MemoryWritePolicy(repository)

        explicit = policy.evaluate(candidate(memory_type="explicit", confidence=0.7))
        assert explicit.decision.action == "create"

        weak = policy.evaluate(candidate(statement="用户可能喜欢热闹的地方", confidence=0.6))
        assert weak.decision.action == "defer"


def test_write_policy_merges_duplicate_statements(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = MemoryRepository(session)
        policy = MemoryWritePolicy(repository)
        first = repository.create_item(candidate())
        result = policy.evaluate(candidate())

        assert result.decision.action == "merge"
        assert result.existing_memory_id == first.memory_id


def test_metadata_memory_retrieval_without_embedding(database: DatabaseEngine) -> None:
    service = MemoryRetrievalService(database)
    with database.session() as session:
        repository = MemoryRepository(session)
        repository.create_item(candidate(statement="用户喜欢博物馆"))
        repository.create_item(candidate(statement="用户喜欢海边"))

    results = service.retrieve("user_a", "博物馆")

    assert len(results) == 1
    assert results[0].statement == "用户喜欢博物馆"


def test_conflict_resolver_prioritizes_explicit_and_scope(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = MemoryRepository(session)
        explicit = repository.create_item(candidate(memory_type="explicit", statement="用户明确喜欢博物馆"))
        semantic = repository.create_item(candidate(statement="用户喜欢博物馆", scope="family"))
        service = MemoryRetrievalService(database)
        memories = [MemoryRepository.to_retrieved(item) for item in [explicit, semantic]]

        decisions = MemoryConflictResolver().resolve(memories, scope="family")

        assert decisions[0].memory.memory_id == explicit.memory_id
        assert decisions[0].priority > decisions[1].priority
