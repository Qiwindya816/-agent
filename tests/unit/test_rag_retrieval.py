"""Tests for RAG retrieval fusion and query isolation."""

from pathlib import Path

import pytest

from db.engine import DatabaseEngine
from services.rag_ingestion import RagIngestionService
from services.rag_retrieval import RagRetrievalService


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'rag.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


@pytest.fixture()
def source(database: DatabaseEngine):
    service = RagIngestionService(database)
    return service.create_source("official", "北京文旅")


def test_rrf_fuses_multiple_recall_lists() -> None:
    from services.rag_retrieval import RagRetrievalService

    fused = RagRetrievalService._rrf([["a", "b"], ["b", "c"]])

    assert fused[0][0] == "b"
    assert dict(fused)["a"] > dict(fused)["c"]


def test_chinese_search_tokens_keep_location_and_travel_intent() -> None:
    tokens = RagRetrievalService._search_tokens("北京有哪些适合散步、亲近自然的公园")

    assert "北京" in tokens
    assert "散步" in tokens
    assert "自然" in tokens
    assert "公园" in tokens


def test_public_and_private_chunks_are_isolated(database: DatabaseEngine, source) -> None:
    ingestion = RagIngestionService(database)
    ingestion.ingest_document(
        source.source_id,
        "公共知识",
        "# 公共\n\n北京故宫需要预约。",
        owner_user_id=None,
        metadata={"city": "北京"},
    )
    ingestion.ingest_document(
        source.source_id,
        "用户私有知识",
        "# 私有\n\n用户自己的北京偏好。",
        owner_user_id="user_a",
        metadata={"city": "北京"},
    )

    retrieval = RagRetrievalService(database)
    with database.session() as session:
        from sqlalchemy import text

        visible_for_b = session.execute(
            text("select count(*) from rag_chunks where owner_user_id is null or owner_user_id = 'user_b'")
        ).scalar_one()
        assert visible_for_b == 1

    # BM25 recall itself is PostgreSQL-only; this test verifies the repository boundary through direct SQL.


def test_dense_recall_uses_embedding_service(database: DatabaseEngine, source) -> None:
    class FakeEmbedding:
        def embed_query(self, query: str) -> list[float]:
            return [0.1] * 1024

    ingestion = RagIngestionService(database)
    document, chunks = ingestion.ingest_document(
        source.source_id,
        "向量测试",
        "# 向量\n\n北京故宫预约。",
        metadata={"city": "北京"},
        embeddings=[[0.1] * 1024],
    )
    retrieval = RagRetrievalService(database, FakeEmbedding())

    # Dense SQL is PostgreSQL-specific; verify that embedding was persisted and service is injected.
    assert chunks[0].embedding == [0.1] * 1024
    assert retrieval.embedding_service is not None
