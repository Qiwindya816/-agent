"""Database-backed AgentState persistence with user/session/trip isolation."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from db.engine import DatabaseEngine, get_database_engine
from repositories.session_repository import MessageRepository, SessionRepository
from repositories.user_repository import UserRepository


class AgentStateRepository:
    """Persist AgentState snapshots and chat messages in the database.

    The structured snapshot is intentionally stored as JSON: this keeps the current
    workflow compatible while user/session/trip ownership remains relational and
    strongly isolated. Trip plan versions can be promoted to dedicated rows later.
    """

    def __init__(self, database: DatabaseEngine | None = None) -> None:
        self.database = database or get_database_engine()

    def load_user_profile(self, user_id: str) -> Any:
        from schemas.user_profile import UserProfile

        with self.database.session() as session:
            users = UserRepository(session)
            user = users.get(user_id)
            if user is None:
                user = users.create(user_id)
            if user.user_profile is None:
                return UserProfile()
            return UserProfile.model_validate(user.user_profile)

    def save_user_profile(self, profile: Any, user_id: str) -> None:
        with self.database.session() as session:
            user = UserRepository(session).require(user_id)
            user.user_profile = profile.model_dump(mode="json", exclude_none=True)

    def update_user_profile(self, updates: Any, user_id: str, **kwargs: Any) -> Any:
        profile = self.load_user_profile(user_id).apply_update(updates, **kwargs)
        self.save_user_profile(profile, user_id)
        return profile

    def load_agent_state(self, session_id: str, user_id: str | None = None) -> Any:
        from schemas.agent_state import AgentState
        from schemas.user_profile import UserProfile

        normalized_user_id = user_id or "default_user"
        with self.database.session() as session:
            record = SessionRepository(session).get(normalized_user_id, session_id)
            if record is None:
                # Distinguish a new session from another user's session ID.
                from sqlalchemy import select

                from db.models import ChatSession

                existing = session.scalar(select(ChatSession).where(ChatSession.session_id == session_id))
                if existing is not None and existing.user_id != normalized_user_id:
                    raise ValueError("该会话不属于当前用户。")
                return AgentState(user_id=normalized_user_id, session_id=session_id)
            if record.agent_state is None:
                return AgentState(
                    user_id=record.user_id,
                    session_id=record.session_id,
                    user_profile=UserProfile.model_validate(record.user_profile or {}),
                )
            state = AgentState.model_validate(record.agent_state)
            state.user_profile = UserProfile.model_validate(record.user_profile or {})
            return state

    def initialize_session(self, user_id: str, session_id: str | None = None) -> Any:
        from schemas.agent_state import AgentState
        from utils.ids import new_session_id

        normalized_user_id = user_id
        state = AgentState(
            user_id=normalized_user_id,
            session_id=session_id or new_session_id(),
            user_profile=self.load_user_profile(normalized_user_id),
        )
        self.save_agent_state(state)
        return state

    def save_agent_state(self, state: Any) -> None:
        from repositories.trip_repository import TripRepository

        state_dict = state.model_dump(mode="json", exclude_none=True)
        profile_dict = state.user_profile.model_dump(mode="json", exclude_none=True)
        with self.database.session() as session:
            users = UserRepository(session)
            if users.get(state.user_id) is None:
                users.create(state.user_id)
            sessions = SessionRepository(session)
            record = sessions.get(state.user_id, state.session_id)
            if record is None:
                sessions.create(
                    state.user_id,
                    state.session_id,
                    title=state.last_intent,
                    agent_state=state_dict,
                    user_profile=profile_dict,
                )
            else:
                sessions.save_state(state.user_id, state.session_id, state_dict, profile_dict)
                record.current_trip_id = state.trip_id

            trips = TripRepository(session)
            if trips.get(state.user_id, state.session_id, state.trip_id) is None:
                trips.create(state.user_id, state.session_id, state.trip_id)
            trips_record = trips.require(state.user_id, state.session_id, state.trip_id)
            trips_record.agent_state = state_dict
            trips_record.user_profile = profile_dict
            trips_record.structured_itinerary = (
                state.structured_itinerary.model_dump(mode="json", exclude_none=True)
                if state.structured_itinerary
                else None
            )

            # Chat history is append-only; preserve existing messages and add only new tail.
            existing_count = self._message_count(session, state.user_id, state.session_id)
            for index, message in enumerate(state.chat_history[existing_count:], start=existing_count):
                MessageRepository(session).add(
                    state.user_id,
                    state.session_id,
                    f"{state.session_id}_{index}",
                    message.role,
                    message.content,
                )

    def _message_count(self, session: Any, user_id: str, session_id: str) -> int:
        return len(MessageRepository(session).list(user_id, session_id))
