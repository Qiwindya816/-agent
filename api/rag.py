"""RAG search and source/document management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import get_current_user, get_database
from db.engine import DatabaseEngine
from repositories.rag_repository import RagRepository
from schemas.api import UserContext
from services.embedding_service import EmbeddingService
from services.rag_ingestion import RagIngestionService
from services.rag_retrieval import RagRetrievalService

router = APIRouter(prefix="/rag", tags=["rag"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    city: str | None = None
    theme: str | None = None
    travel_days: int | None = None
    audience: str | None = None
    top_k: int | None = None


@router.post("/search")
def search(
    request: SearchRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[dict[str, Any]]:
    service = RagRetrievalService(database, EmbeddingService())
    results = service.search(
        user.user_id,
        request.query,
        city=request.city,
        theme=request.theme,
        travel_days=request.travel_days,
        audience=request.audience,
        top_k=request.top_k,
    )
    return [
        {
            "rank": item.rank,
            "score": item.score,
            "chunk_text": item.chunk_text,
            "chunk_type": item.chunk_type,
            "source_name": item.source_name,
            "source_url": item.source_url,
            "fetched_at": item.fetched_at,
        }
        for item in results
    ]


class SourceCreateRequest(BaseModel):
    source_type: str
    name: str
    url: str | None = None
    license_name: str | None = None
    authorization_status: str = "authorized"
    owner_user_id: str | None = None


class DocumentIngestRequest(BaseModel):
    title: str
    content: str
    document_type: str = "fact"
    metadata: dict[str, Any] = Field(default_factory=dict)
    owner_user_id: str | None = None
    embed: bool = True


@router.post("/sources", status_code=201)
def create_source(
    request: SourceCreateRequest,
    _: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, Any]:
    service = RagIngestionService(database)
    source = service.create_source(
        request.source_type,
        request.name,
        url=request.url,
        license_name=request.license_name,
        authorization_status=request.authorization_status,
        owner_user_id=request.owner_user_id,
    )
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "name": source.name,
        "authorization_status": source.authorization_status,
    }


@router.post("/sources/{source_id}/documents", status_code=201)
def ingest_document(
    source_id: str,
    request: DocumentIngestRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, Any]:
    service = RagIngestionService(database)
    chunks = service.chunker.chunk(request.content, request.document_type, request.metadata)
    embeddings = None
    if request.embed:
        from services.embedding_service import EmbeddingService

        embeddings = EmbeddingService().embed_texts([item.chunk_text for item in chunks])
    document, chunk_rows = service.ingest_document(
        source_id,
        request.title,
        request.content,
        document_type=request.document_type,
        owner_user_id=request.owner_user_id,
        metadata=request.metadata,
        embeddings=embeddings,
    )
    return {
        "document_id": document.document_id,
        "chunk_count": len(chunk_rows),
        "raw_file_path": document.raw_file_path,
    }


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, bool]:
    with database.session() as session:
        deleted = RagRepository(session).delete_document(document_id)
    return {"deleted": deleted}


@router.get("/sources")
def list_sources(
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[dict[str, Any]]:
    with database.session() as session:
        items = RagRepository(session).list_sources()
    return [
        {
            "source_id": item.source_id,
            "source_type": item.source_type,
            "name": item.name,
            "url": item.url,
            "authorization_status": item.authorization_status,
            "owner_user_id": item.owner_user_id,
        }
        for item in items
    ]
