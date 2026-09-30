"""SQLAlchemy engine and session management."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings


class DatabaseEngine:
    """Application database engine and session factory."""

    def __init__(self, database_url: str | None = None, *, echo: bool | None = None) -> None:
        settings = get_settings()
        self.url = database_url or settings.database_url
        self.echo = settings.database_echo if echo is None else echo
        self.engine = create_engine(self.url, echo=self.echo, future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> None:
        """Create tables for development and tests. Migrations are preferred outside tests."""
        from db import Base

        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_engine: DatabaseEngine | None = None


def get_database_engine() -> DatabaseEngine:
    """Return the process-wide database engine, creating it lazily."""
    global _engine
    if _engine is None:
        _engine = DatabaseEngine()
    return _engine


def reset_database_engine(database_url: str | None = None) -> DatabaseEngine:
    """Reset the process-wide engine, mainly for tests and CLI setup."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = DatabaseEngine(database_url)
    return _engine
