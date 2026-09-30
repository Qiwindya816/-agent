"""PostgreSQL checkpoint factory tests."""

import pytest

from services import checkpoints
from services.checkpoints import build_checkpointer


def test_build_checkpointer_uses_postgres_for_postgresql_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class Settings:
        checkpoint_backend = "postgresql"
        database_url = "postgresql+psycopg://user:password@localhost:5432/db"

    created = {}

    class FakeConnection:
        pass

    class FakePostgresSaver:
        def __init__(self, connection):
            created["connection"] = connection

        def setup(self):
            created["setup"] = True

    monkeypatch.setattr(checkpoints, "get_settings", lambda: Settings())
    monkeypatch.setattr(checkpoints.psycopg, "connect", lambda *args, **kwargs: FakeConnection())
    checkpoints.PostgresSaver = FakePostgresSaver
    try:
        saver = build_checkpointer(setup=True)
    finally:
        del checkpoints.PostgresSaver

    assert isinstance(saver, FakePostgresSaver)
    assert created["setup"] is True


def test_build_checkpointer_falls_back_to_memory_for_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    class Settings:
        checkpoint_backend = "postgresql"
        database_url = "sqlite+pysqlite:///./travelmind.db"

    from langgraph.checkpoint.memory import InMemorySaver

    monkeypatch.setattr(checkpoints, "get_settings", lambda: Settings())
    assert isinstance(build_checkpointer(), InMemorySaver)
