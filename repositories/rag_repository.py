"""CRUD operations for RAG sources, documents, chunks, and ingestion jobs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import RagChunk, RagDocument, RagIngestionJob, RagSource


class RagRepository:
    """RAG persistence operations with source ownership boundaries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_source(self, source_id: str) -> RagSource | None:
        return self.session.get(RagSource, source_id)

    def list_sources(self, owner_user_id: str | None = None) -> list[RagSource]:
        statement = select(RagSource)
        if owner_user_id is not None:
            statement = statement.where(RagSource.owner_user_id == owner_user_id)
        return list(self.session.scalars(statement.order_by(RagSource.created_at)))

    def delete_source(self, source_id: str) -> bool:
        source = self.get_source(source_id)
        if source is None:
            return False
        self.session.delete(source)
        self.session.flush()
        return True

    def get_document(self, document_id: str) -> RagDocument | None:
        return self.session.get(RagDocument, document_id)

    def list_documents(self, source_id: str) -> list[RagDocument]:
        return list(
            self.session.scalars(
                select(RagDocument)
                .where(RagDocument.source_id == source_id)
                .order_by(RagDocument.created_at)
            )
        )

    def delete_document(self, document_id: str) -> bool:
        document = self.get_document(document_id)
        if document is None:
            return False
        self.session.delete(document)
        self.session.flush()
        return True

    def list_chunks(self, document_id: str) -> list[RagChunk]:
        return list(
            self.session.scalars(
                select(RagChunk)
                .where(RagChunk.document_id == document_id)
                .order_by(RagChunk.created_at)
            )
        )

    def list_jobs(self, source_id: str) -> list[RagIngestionJob]:
        return list(
            self.session.scalars(
                select(RagIngestionJob)
                .where(RagIngestionJob.source_id == source_id)
                .order_by(RagIngestionJob.started_at)
            )
        )

    def chunks_missing_embeddings(self) -> list[RagChunk]:
        return list(
            self.session.scalars(
                select(RagChunk)
                .where(RagChunk.embedding.is_(None))
                .order_by(RagChunk.created_at)
            )
        )
