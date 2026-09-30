"""Tests for RAG repository CRUD and cascade deletion."""

from pathlib import Path

import pytest

from db.engine import DatabaseEngine
from repositories.rag_repository import RagRepository
from services.rag_ingestion import RagIngestionService


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'rag.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def test_rag_repository_lists_and_deletes_documents(database: DatabaseEngine) -> None:
    ingestion = RagIngestionService(database)
    source = ingestion.create_source("official", "北京文旅")
    document, chunks = ingestion.ingest_document(
        source.source_id,
        "故宫",
        "# 故宫\n\n需要预约。",
        metadata={"city": "北京"},
    )

    with database.session() as session:
        repository = RagRepository(session)
        assert repository.get_source(source.source_id) is not None
        assert repository.get_document(document.document_id) is not None
        assert len(repository.list_documents(source.source_id)) == 1
        assert len(repository.list_chunks(document.document_id)) == len(chunks)
        assert repository.delete_document(document.document_id) is True

    with database.session() as session:
        repository = RagRepository(session)
        assert repository.get_document(document.document_id) is None
        assert repository.list_chunks(document.document_id) == []


def test_rag_repository_deleting_source_cascades_documents_and_chunks(database: DatabaseEngine) -> None:
    ingestion = RagIngestionService(database)
    source = ingestion.create_source("official", "北京文旅")
    document, _ = ingestion.ingest_document(
        source.source_id,
        "故宫",
        "# 故宫\n\n需要预约。",
        metadata={"city": "北京"},
    )

    with database.session() as session:
        assert RagRepository(session).delete_source(source.source_id) is True

    with database.session() as session:
        repository = RagRepository(session)
        assert repository.get_source(source.source_id) is None
        assert repository.get_document(document.document_id) is None
        assert repository.list_chunks(document.document_id) == []
