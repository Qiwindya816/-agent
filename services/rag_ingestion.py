"""RAG source, document, and chunk ingestion pipeline."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import get_settings
from db.engine import DatabaseEngine, get_database_engine
from db.models import RagChunk, RagDocument, RagIngestionJob, RagSource
from services.rag_chunker import RagChunker


class RagIngestionService:
    """Register sources, deduplicate documents, chunk content, and store embeddings."""

    def __init__(self, database: DatabaseEngine | None = None, chunker: RagChunker | None = None) -> None:
        self.database = database or get_database_engine()
        self.chunker = chunker or RagChunker()

    def create_source(
        self,
        source_type: str,
        name: str,
        *,
        url: str | None = None,
        license_name: str | None = None,
        authorization_status: str = "authorized",
        owner_user_id: str | None = None,
    ) -> RagSource:
        with self.database.session() as session:
            source = RagSource(
                source_id=f"src_{uuid4().hex[:16]}",
                source_type=source_type,
                name=name,
                url=url,
                license=license_name,
                authorization_status=authorization_status,
                owner_user_id=owner_user_id,
            )
            session.add(source)
            session.flush()
            session.refresh(source)
            return source

    def ingest_document(
        self,
        source_id: str,
        title: str,
        content: str,
        *,
        document_type: str = "fact",
        owner_user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        embeddings: list[list[float]] | None = None,
        published_at: datetime | None = None,
    ) -> tuple[RagDocument, list[RagChunk]]:
        """Ingest a document, returning document and chunks.

        ``embeddings`` is optional to keep deterministic ingestion testable. In
        production, callers should first call EmbeddingService.embed_texts.
        """
        content_hash = self.content_hash(content)
        with self.database.session() as session:
            job = RagIngestionJob(
                job_id=f"job_{uuid4().hex[:16]}",
                source_id=source_id,
                status="running",
                started_at=datetime.now(),
            )
            session.add(job)
            session.flush()

            existing = session.scalar(
                select(RagDocument).where(
                    RagDocument.source_id == source_id,
                    RagDocument.content_hash == content_hash,
                )
            )
            if existing is not None:
                job.status = "skipped"
                job.document_id = existing.document_id
                job.finished_at = datetime.now()
                session.refresh(existing)
                return existing, []

            raw_path = self._store_raw(source_id, title, content)
            document = RagDocument(
                document_id=f"doc_{uuid4().hex[:16]}",
                source_id=source_id,
                owner_user_id=owner_user_id,
                content_hash=content_hash,
                raw_file_path=str(raw_path),
                title=title,
                published_at=published_at,
                status="active",
            )
            session.add(document)
            session.flush()

            chunks = self._create_chunks(
                session,
                document,
                content,
                document_type,
                metadata or {},
                embeddings or [],
            )
            job.document_id = document.document_id
            job.status = "completed"
            job.finished_at = datetime.now()
            session.refresh(document)
            chunk_rows = list(chunks)
            return document, chunk_rows

    def _create_chunks(
        self,
        session: Session,
        document: RagDocument,
        content: str,
        document_type: str,
        metadata: dict[str, Any],
        embeddings: list[list[float]],
    ) -> list[RagChunk]:
        chunk_inputs = self.chunker.chunk(content, document_type, metadata)
        if embeddings and len(embeddings) != len(chunk_inputs):
            raise ValueError("Embedding count must match chunk count.")
        rows: list[RagChunk] = []
        for index, chunk_input in enumerate(chunk_inputs):
            values = dict(chunk_input.metadata)
            row = RagChunk(
                chunk_id=f"chunk_{uuid4().hex[:16]}",
                document_id=document.document_id,
                owner_user_id=document.owner_user_id,
                chunk_text=chunk_input.chunk_text,
                chunk_type=chunk_input.chunk_type,
                city=values.get("city"),
                district=values.get("district"),
                poi_id=values.get("poi_id"),
                latitude=values.get("latitude"),
                longitude=values.get("longitude"),
                theme=values.get("theme"),
                travel_days=values.get("travel_days"),
                audience=values.get("audience"),
                season=values.get("season"),
                price_level=values.get("price_level"),
                metadata_json=values,
                embedding=embeddings[index] if embeddings else None,
            )
            session.add(row)
            rows.append(row)
        session.flush()
        return rows

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _store_raw(self, source_id: str, title: str, content: str) -> Path:
        root = get_settings().rag_raw_dir
        directory = root / source_id
        directory.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(character if character.isalnum() or character in "-_ " else "_" for character in title)
        path = directory / f"{safe_title}.txt"
        path.write_text(content, encoding="utf-8")
        return path
