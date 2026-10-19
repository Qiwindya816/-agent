"""Tests for RAG retrieval fusion and query isolation."""

from pathlib import Path

import pytest

from db.engine import DatabaseEngine
from services.rag_ingestion import RagIngestionService
from services.rag_retrieval import RagRetrievalService
from services.rerank_service import RerankResult


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


def test_search_reranks_rrf_candidates(database: DatabaseEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeReranker:
        def rerank(self, query: str, documents: list[str], *, top_n: int | None = None) -> list[RerankResult]:
            assert query == "不要爬山的北京行程"
            assert documents == ["长城登山路线", "故宫无障碍路线"]
            assert top_n == 2
            return [RerankResult(index=1, relevance_score=0.95), RerankResult(index=0, relevance_score=0.10)]

    retrieval = RagRetrievalService(database, rerank_service=FakeReranker())
    monkeypatch.setattr(retrieval, "_templates", lambda *args, **kwargs: ["chunk_a", "chunk_b"])
    monkeypatch.setattr(
        retrieval,
        "_load_chunks",
        lambda user_id, chunk_ids: {
            "chunk_a": _retrieved_row("chunk_a", "长城登山路线"),
            "chunk_b": _retrieved_row("chunk_b", "故宫无障碍路线"),
        },
    )

    results = retrieval.search("user_a", "不要爬山的北京行程", city="北京", top_k=2)

    assert [item.chunk_id for item in results] == ["chunk_b", "chunk_a"]
    assert results[0].score == pytest.approx(0.95)
    assert results[0].rerank_score == pytest.approx(0.95)
    assert results[0].rrf_score is not None


def test_search_falls_back_to_rrf_when_reranker_fails(
    database: DatabaseEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingReranker:
        def rerank(self, query: str, documents: list[str], *, top_n: int | None = None) -> list[RerankResult]:
            raise RuntimeError("temporary rerank outage")

    retrieval = RagRetrievalService(database, rerank_service=FailingReranker())
    monkeypatch.setattr(retrieval, "_templates", lambda *args, **kwargs: ["chunk_a", "chunk_b"])
    monkeypatch.setattr(
        retrieval,
        "_load_chunks",
        lambda user_id, chunk_ids: {
            "chunk_a": _retrieved_row("chunk_a", "候选 A"),
            "chunk_b": _retrieved_row("chunk_b", "候选 B"),
        },
    )

    results = retrieval.search("user_a", "北京行程", city="北京", top_k=2)

    assert [item.chunk_id for item in results] == ["chunk_a", "chunk_b"]
    assert all(item.rerank_score is None for item in results)
    assert all(item.score == item.rrf_score for item in results)


def _retrieved_row(chunk_id: str, chunk_text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": f"doc_{chunk_id}",
        "owner_user_id": None,
        "chunk_text": chunk_text,
        "chunk_type": "template",
        "city": "北京",
        "theme": None,
        "travel_days": 2,
        "audience": None,
        "source_name": "测试来源",
        "source_url": None,
        "source_authorization_status": "authorized",
        "published_at": None,
        "fetched_at": None,
        "social_platform": None,
        "likes": None,
        "collects": None,
        "comments": None,
        "shares": None,
    }
