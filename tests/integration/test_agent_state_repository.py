"""Tests for database-backed AgentState persistence."""

from pathlib import Path

import pytest

from db.engine import DatabaseEngine
from memory import memory_manager
from schemas.agent_state import ChatMessage
from repositories.agent_state_repository import AgentStateRepository


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'state.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def test_agent_state_round_trip_and_isolation(database: DatabaseEngine) -> None:
    store = AgentStateRepository(database)
    memory_manager.use_database_state_store(store)
    try:
        state = store.initialize_session("user_a", "session_a")
        state.chat_history.append(ChatMessage(role="user", content="hello"))
        store.save_agent_state(state)

        loaded = store.load_agent_state("session_a", "user_a")
        assert loaded.user_id == "user_a"
        assert loaded.chat_history[-1].content == "hello"

        with pytest.raises(ValueError):
            store.load_agent_state("session_a", "user_b")
    finally:
        memory_manager.use_database_state_store(None)


def test_agent_state_repository_persists_trip_and_profile(database: DatabaseEngine) -> None:
    from schemas.user_profile import UserProfile

    store = AgentStateRepository(database)
    state = store.initialize_session("user_a", "session_a")
    state.user_profile = UserProfile(interests=["history"])
    store.save_user_profile(state.user_profile, "user_a")
    store.save_agent_state(state)

    loaded_profile = store.load_user_profile("user_a")
    assert loaded_profile.interests == ["history"]

    with database.session() as session:
        from db.models import Trip

        trip = session.get(Trip, state.trip_id)
        assert trip is not None
        assert trip.user_id == "user_a"
        assert trip.session_id == "session_a"
