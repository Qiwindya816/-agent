"""Database model and table creation tests."""

from pathlib import Path

from db import Base
from db.engine import DatabaseEngine


def test_core_tables_are_created(tmp_path: Path) -> None:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'travelmind.db'}")
    engine.create_all()

    expected = {
        "users",
        "chat_sessions",
        "chat_messages",
        "trips",
        "trip_plan_versions",
        "trip_feedback",
        "memory_items",
        "memory_evidence",
        "rag_sources",
        "rag_documents",
        "rag_chunks",
        "tool_calls",
        "provider_health",
    }

    try:
        assert expected.issubset(set(Base.metadata.tables.keys()))
        with engine.engine.connect() as connection:
            table_names = set(engine.engine.dialect.get_table_names(connection))
        assert table_names.issuperset(expected)
    finally:
        engine.dispose()
