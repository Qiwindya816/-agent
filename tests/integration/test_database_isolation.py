"""Isolation tests for user/session/trip and user-owned data."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from db import Base
from db.engine import DatabaseEngine
from db.models import ChatSession, RagChunk, User
from repositories.memory_rag_tool_repository import MemoryRepository, RagRepository
from repositories.session_repository import MessageRepository, SessionRepository
from repositories.trip_repository import PlanVersionRepository, TripRepository
from repositories.user_repository import UserRepository


@pytest.fixture()
def engine(tmp_path: Path) -> DatabaseEngine:
    database = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'travelmind-test.db'}")
    database.create_all()
    yield database
    database.dispose()


@pytest.fixture()
def session(engine: DatabaseEngine) -> Session:
    with engine.session() as db_session:
        yield db_session


def seed_user_session(session: Session, user_id: str, session_id: str) -> None:
    users = UserRepository(session)
    if users.get(user_id) is None:
        users.create(user_id, display_name=user_id)
    SessionRepository(session).create(user_id, session_id)


def test_user_sessions_are_isolated(session: Session) -> None:
    seed_user_session(session, "user_a", "session_a")
    seed_user_session(session, "user_b", "session_b")

    assert SessionRepository(session).get("user_a", "session_b") is None
    assert SessionRepository(session).get("user_b", "session_a") is None
    assert SessionRepository(session).list("user_a") == [session.get(ChatSession, "session_a")]


def test_messages_are_isolated_by_user_and_session(session: Session) -> None:
    seed_user_session(session, "user_messages_a", "session_messages_a")
    seed_user_session(session, "user_messages_a", "session_messages_b")
    messages = MessageRepository(session)

    messages.add("user_messages_a", "session_messages_a", "message_a", "user", "hello")
    messages.add("user_messages_a", "session_messages_b", "message_b", "user", "hello")

    assert messages.get("user_messages_a", "session_messages_a", "message_b") is None
    assert messages.get("user_messages_a", "session_messages_b", "message_a") is None
    assert len(messages.list("user_messages_a", "session_messages_a")) == 1


def test_trips_are_isolated_by_session(session: Session) -> None:
    seed_user_session(session, "user_trips_a", "session_trips_a")
    seed_user_session(session, "user_trips_a", "session_trips_b")
    trips = TripRepository(session)

    trips.create("user_trips_a", "session_trips_a", "trip_a", destination="Beijing")
    trips.create("user_trips_a", "session_trips_b", "trip_b", destination="Shanghai")

    assert trips.get("user_trips_a", "session_trips_a", "trip_b") is None
    assert trips.get("user_trips_a", "session_trips_b", "trip_a") is None
    assert [trip.trip_id for trip in trips.list("user_trips_a", "session_trips_a")] == ["trip_a"]


def test_trip_versions_are_immutable_and_scoped(session: Session) -> None:
    seed_user_session(session, "user_a", "session_a")
    trips = TripRepository(session)
    versions = PlanVersionRepository(session)
    trips.create("user_a", "session_a", "trip_a")

    first = versions.create("user_a", "session_a", "trip_a", "version_a", {"day": 1})
    second = versions.create("user_a", "session_a", "trip_a", "version_b", {"day": 2})

    assert first.version_number == 1
    assert second.version_number == 2
    assert [version.version_number for version in versions.list("user_a", "session_a", "trip_a")] == [1, 2]


def test_memory_is_isolated_by_user(session: Session) -> None:
    UserRepository(session).create("user_a")
    UserRepository(session).create("user_b")
    memories = MemoryRepository(session)
    memories.create("user_a", "memory_a", "explicit", "food", "Likes museums")
    memories.create("user_b", "memory_b", "explicit", "food", "Likes beaches")

    assert memories.get("user_a", "memory_b") is None
    assert memories.get("user_b", "memory_a") is None
    assert len(memories.list("user_a")) == 1


def test_rag_public_and_private_visibility(session: Session) -> None:
    UserRepository(session).create("user_a")
    UserRepository(session).create("user_b")
    session.add(RagChunk(chunk_id="public", document_id="doc", owner_user_id=None, chunk_text="public", chunk_type="fact"))
    session.add(RagChunk(chunk_id="private_a", document_id="doc", owner_user_id="user_a", chunk_text="a", chunk_type="guide"))

    visible = RagRepository(session).visible_chunks("user_b")

    assert [chunk.chunk_id for chunk in visible] == ["public"]


def test_deleting_user_cascades_sessions_trips_and_memory(session: Session) -> None:
    seed_user_session(session, "user_a", "session_a")
    trips = TripRepository(session)
    memories = MemoryRepository(session)
    trips.create("user_a", "session_a", "trip_a")
    memories.create("user_a", "memory_a", "explicit", "food", "Likes museums")

    assert UserRepository(session).delete("user_a") is True
    session.flush()
    session.expire_all()

    assert session.get(User, "user_a") is None
    assert session.get(ChatSession, "session_a") is None
    assert trips.get("user_a", "session_a", "trip_a") is None
    assert memories.get("user_a", "memory_a") is None
