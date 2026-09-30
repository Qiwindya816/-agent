"""Tests for RAG chunking and ingestion."""

from pathlib import Path

import pytest

from db.engine import DatabaseEngine
from services.rag_chunker import RagChunker
from services.rag_ingestion import RagIngestionService


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    # SQLite is used for ingestion/chunk tests. Vector column is present in ORM but not queried here.
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'rag.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def test_fact_document_is_chunked_by_paragraph() -> None:
    chunks = RagChunker().chunk(
        "# 故宫\n\n开放时间为周二至周日。\n\n门票需要提前预约。",
        "fact",
        {"city": "北京", "poi_id": "B000A8UIN8"},
    )

    assert len(chunks) == 2
    assert all(chunk.chunk_type == "fact" for chunk in chunks)
    assert chunks[0].metadata["poi_id"] == "B000A8UIN8"
    assert chunks[0].metadata["heading"] == "故宫"


def test_guide_document_is_chunked_by_heading() -> None:
    chunks = RagChunker().chunk(
        "# 交通\n住在地铁站附近。\n\n# 餐饮\n推荐本地老店。",
        "guide",
        {"city": "成都"},
    )

    assert len(chunks) == 2
    assert chunks[0].metadata["heading"] == "交通"
    assert chunks[1].metadata["heading"] == "餐饮"


def test_template_is_chunked_by_day() -> None:
    chunks = RagChunker().chunk(
        "Day 1\n上午故宫，下午景山。\nDay 2\n上午国博，下午王府井。",
        "template",
        {"city": "北京", "travel_days": 2},
    )

    assert len(chunks) == 2
    assert chunks[0].metadata["day"] == "1"
    assert chunks[1].metadata["day"] == "2"


def test_ingestion_creates_document_and_chunks(database: DatabaseEngine, tmp_path: Path) -> None:
    service = RagIngestionService(database)
    source = service.create_source("official", "北京文旅", url="https://example.com")

    document, chunks = service.ingest_document(
        source.source_id,
        "故宫开放信息",
        "# 故宫\n\n周一闭馆。\n\n需要提前预约。",
        document_type="fact",
        metadata={"city": "北京", "poi_id": "B000A8UIN8"},
    )

    assert document.status == "active"
    assert len(chunks) == 2
    assert chunks[0].city == "北京"
    assert chunks[0].poi_id == "B000A8UIN8"
    assert document.raw_file_path is not None


def test_ingestion_skips_duplicate_content(database: DatabaseEngine) -> None:
    service = RagIngestionService(database)
    source = service.create_source("official", "北京文旅")
    content = "# 故宫\n\n周一闭馆。"

    first, first_chunks = service.ingest_document(source.source_id, "故宫", content, metadata={"city": "北京"})
    second, second_chunks = service.ingest_document(source.source_id, "故宫", content, metadata={"city": "北京"})

    assert len(first_chunks) == 1
    assert second.document_id == first.document_id
    assert second_chunks == []
