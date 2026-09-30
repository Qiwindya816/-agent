"""Tests for user control over long-term memory: evidence, clear, export, and settings."""

from pathlib import Path
from typing import Any

import pytest

from db.engine import DatabaseEngine
from repositories.memory_repository import MemoryRepository
from repositories.user_repository import UserRepository
from schemas.memory import MemoryCandidate


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'memory-control.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def candidate(user_id: str = "control_user", **kwargs: Any) -> MemoryCandidate:
    values = {
        "user_id": user_id,
        "memory_type": "explicit",
        "category": "interests",
        "statement": "用户喜欢博物馆",
        "evidence_text": "用户说：请记住我喜欢博物馆",
        "evidence_type": "explicit_statement",
        "confidence": 0.98,
    }
    values.update(kwargs)
    return MemoryCandidate(**values)


def test_user_can_list_memory_evidence(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = MemoryRepository(session)
        item = repository.create_item(candidate())

        evidence = repository.list_evidence("control_user", item.memory_id)

        assert len(evidence) == 1
        assert evidence[0].evidence_text == "用户说：请记住我喜欢博物馆"
        assert repository.list_evidence("other_user", item.memory_id) == []


def test_user_can_clear_all_memories(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = MemoryRepository(session)
        repository.create_item(candidate(statement="用户喜欢博物馆"))
        repository.create_item(candidate(statement="用户喜欢历史街区"))

        deleted = repository.clear_items("control_user")

        assert deleted == 2
        assert repository.list_items("control_user") == []


def test_user_can_export_memories_with_evidence(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = MemoryRepository(session)
        repository.create_item(candidate())

        exported = repository.export_items("control_user")

        assert exported[0]["statement"] == "用户喜欢博物馆"
        assert exported[0]["evidence"][0]["evidence_type"] == "explicit_statement"


def test_user_settings_can_disable_personalization_and_memory(database: DatabaseEngine) -> None:
    with database.session() as session:
        repository = UserRepository(session)
        repository.create("control_user")

        user = repository.update_settings(
            "control_user",
            personalization_enabled=False,
            long_term_memory_enabled=False,
        )

        assert user.personalization_enabled is False
        assert user.long_term_memory_enabled is False

        restored = repository.update_settings(
            "control_user",
            personalization_enabled=True,
            long_term_memory_enabled=True,
        )
        assert restored.personalization_enabled is True
        assert restored.long_term_memory_enabled is True


def test_deleting_user_cascades_memories_and_evidence(database: DatabaseEngine) -> None:
    with database.session() as session:
        memory_repository = MemoryRepository(session)
        memory_repository.create_item(candidate())
        user_repository = UserRepository(session)

        assert user_repository.delete("control_user") is True
        session.flush()
        session.expire_all()

        assert memory_repository.list_items("control_user") == []
