"""Tests for trip feedback persistence."""

from pathlib import Path

import pytest

from db.engine import DatabaseEngine
from repositories.session_repository import SessionRepository
from repositories.trip_feedback_repository import TripFeedbackRepository
from repositories.trip_repository import TripRepository
from repositories.user_repository import UserRepository
from services.itinerary_renderer import render_itinerary_markdown
from schemas.itinerary import Itinerary


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'feedback.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def test_trip_feedback_is_isolated_by_user(database: DatabaseEngine) -> None:
    with database.session() as session:
        users = UserRepository(session)
        users.create("user_a")
        users.create("user_b")
        SessionRepository(session).create("user_a", "session_a")
        SessionRepository(session).create("user_b", "session_b")
        TripRepository(session).create("user_a", "session_a", "trip_a")
        TripRepository(session).create("user_b", "session_b", "trip_b")

        feedback = TripFeedbackRepository(session)
        feedback.create("user_a", "trip_a", feedback_type="reject", activity_id="activity_1", reason="太累")

        assert len(feedback.list_for_trip("user_a", "trip_a")) == 1
        assert feedback.list_for_trip("user_b", "trip_a") == []


def test_trip_feedback_rejects_invalid_type(database: DatabaseEngine) -> None:
    with database.session() as session:
        with pytest.raises(ValueError):
            TripFeedbackRepository(session).create("user_a", "trip_a", feedback_type="invalid")
