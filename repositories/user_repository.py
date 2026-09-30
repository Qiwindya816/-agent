"""User-scoped repository operations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import User


class UserRepository:
    """Operations on users. User IDs are the top-level isolation boundary."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, user_id: str, display_name: str | None = None) -> User:
        user = User(user_id=user_id, display_name=display_name)
        self.session.add(user)
        self.session.flush()
        return user

    def get(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def require(self, user_id: str) -> User:
        user = self.get(user_id)
        if user is None:
            raise LookupError(f"User not found: {user_id}")
        return user

    def update_settings(
        self,
        user_id: str,
        *,
        personalization_enabled: bool | None = None,
        long_term_memory_enabled: bool | None = None,
    ) -> User:
        user = self.require(user_id)
        if personalization_enabled is not None:
            user.personalization_enabled = personalization_enabled
        if long_term_memory_enabled is not None:
            user.long_term_memory_enabled = long_term_memory_enabled
        self.session.flush()
        return user

    def list_sessions(self, user_id: str):
        from db.models import ChatSession

        user = self.require(user_id)
        return sorted(user.sessions, key=lambda item: item.created_at)

    def delete(self, user_id: str) -> bool:
        user = self.get(user_id)
        if user is None:
            return False
        self.session.delete(user)
        self.session.flush()
        return True
