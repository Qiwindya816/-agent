"""Session and message repositories with user isolation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ChatMessage, ChatSession


class SessionRepository:
    """Session operations that always require a user_id boundary."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        user_id: str,
        session_id: str,
        title: str | None = None,
        agent_state: dict | None = None,
        user_profile: dict | None = None,
    ) -> ChatSession:
        from repositories.user_repository import UserRepository

        UserRepository(self.session).require(user_id)
        chat_session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            title=title,
            agent_state=agent_state,
            user_profile=user_profile,
        )
        self.session.add(chat_session)
        self.session.flush()
        return chat_session

    def get(self, user_id: str, session_id: str) -> ChatSession | None:
        chat_session = self.session.get(ChatSession, session_id)
        if chat_session is None or chat_session.user_id != user_id:
            return None
        return chat_session

    def require(self, user_id: str, session_id: str) -> ChatSession:
        chat_session = self.get(user_id, session_id)
        if chat_session is None:
            raise LookupError(f"Session not found for user {user_id}: {session_id}")
        return chat_session

    def list(self, user_id: str) -> list[ChatSession]:
        statement = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at)
        return list(self.session.scalars(statement))

    def set_current_trip(self, user_id: str, session_id: str, trip_id: str | None) -> ChatSession:
        chat_session = self.require(user_id, session_id)
        chat_session.current_trip_id = trip_id
        self.session.flush()
        return chat_session

    def delete(self, user_id: str, session_id: str) -> bool:
        chat_session = self.get(user_id, session_id)
        if chat_session is None:
            return False
        self.session.delete(chat_session)
        self.session.flush()
        return True

    def save_state(self, user_id: str, session_id: str, agent_state: dict, user_profile: dict) -> ChatSession:
        chat_session = self.require(user_id, session_id)
        chat_session.agent_state = agent_state
        chat_session.user_profile = user_profile
        self.session.flush()
        return chat_session

class MessageRepository:
    """Message operations bounded by user_id and session_id."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        user_id: str,
        session_id: str,
        message_id: str,
        role: str,
        content: str,
        structured_payload: dict | None = None,
        token_count: int | None = None,
    ) -> ChatMessage:
        SessionRepository(self.session).require(user_id, session_id)
        message = ChatMessage(
            message_id=message_id,
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            structured_payload=structured_payload,
            token_count=token_count,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def get(self, user_id: str, session_id: str, message_id: str) -> ChatMessage | None:
        message = self.session.get(ChatMessage, message_id)
        if message is None or message.user_id != user_id or message.session_id != session_id:
            return None
        return message

    def list(self, user_id: str, session_id: str) -> list[ChatMessage]:
        SessionRepository(self.session).require(user_id, session_id)
        statement = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        return list(self.session.scalars(statement))
