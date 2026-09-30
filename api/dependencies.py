"""FastAPI dependency factories with explicit user isolation."""

from __future__ import annotations

from fastapi import Depends, Header

from db.engine import DatabaseEngine, get_database_engine
from schemas.api import UserContext
from utils.ids import validate_user_id


def get_database() -> DatabaseEngine:
    """Return the process-wide database engine."""
    return get_database_engine()


def get_current_user(x_user_id: str | None = Header(default=None)) -> UserContext:
    """Resolve the current user from the X-User-ID header.

    Authentication is intentionally pluggable: the first version accepts an
    explicit local user header and validates its format. Production deployments
    can replace this dependency with JWT/session authentication.
    """
    if not x_user_id:
        # Local development default keeps the API usable without auth.
        return UserContext(user_id="default_user")
    return UserContext(user_id=validate_user_id(x_user_id))
