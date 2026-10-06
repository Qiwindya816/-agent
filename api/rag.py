"""提供 FastAPI 接口、依赖注入与请求处理；本文件负责 `rag` 相关实现。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
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
    """定义 search 请求的数据结构。"""
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
    """执行带用户隔离和可选过滤条件的检索。"""
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
            "source_authorization_status": item.source_authorization_status,
            "published_at": item.published_at,
            "fetched_at": item.fetched_at,
            "social_platform": item.social_platform,
            "engagement": {
                "likes": item.likes,
                "collects": item.collects,
                "comments": item.comments,
                "shares": item.shares,
            } if item.social_platform else None,
        }
        for item in results
    ]


class SourceCreateRequest(BaseModel):
    """定义创建 RAG 知识来源时允许提交的字段。"""
    source_type: str
    name: str
    url: str | None = None
    license_name: str | None = None
    authorization_status: str = "authorized"


class DocumentIngestRequest(BaseModel):
    """定义向指定知识来源导入文档时的请求字段。"""
    title: str
    content: str
    document_type: str = "fact"
    metadata: dict[str, Any] = Field(default_factory=dict)
    embed: bool = True


@router.post("/sources", status_code=201)
def create_source(
    request: SourceCreateRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, Any]:
    """创建知识来源，并保持相关状态或持久化数据一致。"""
    from repositories.user_repository import UserRepository

    with database.session() as session:
        users = UserRepository(session)
        if users.get(user.user_id) is None:
            users.create(user.user_id)
    service = RagIngestionService(database)
    source = service.create_source(
        request.source_type,
        request.name,
        url=request.url,
        license_name=request.license_name,
        authorization_status=request.authorization_status,
        owner_user_id=user.user_id,
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
    """校验知识来源所有权，并切块、向量化和持久化文档。"""
    with database.session() as session:
        source = RagRepository(session).get_owned_source(user.user_id, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="RAG source not found")
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
        owner_user_id=user.user_id,
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
    """删除文档，并保持相关状态或持久化数据一致。"""
    with database.session() as session:
        deleted = RagRepository(session).delete_owned_document(user.user_id, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="RAG document not found")
    return {"deleted": deleted}


@router.get("/sources")
def list_sources(
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[dict[str, Any]]:
    """列出知识来源列表并返回符合当前作用域的结果。"""
    with database.session() as session:
        items = RagRepository(session).list_visible_sources(user.user_id)
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


@router.get("/documents")
def list_documents(
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[dict[str, Any]]:
    """列出文档列表并返回符合当前作用域的结果。"""
    with database.session() as session:
        repository = RagRepository(session)
        items = repository.list_visible_documents(user.user_id)
        return [
            {
                "document_id": item.document_id,
                "source_id": item.source_id,
                "title": item.title,
                "status": item.status,
                "owner_user_id": item.owner_user_id,
                "created_at": item.created_at,
                "is_public": item.owner_user_id is None,
                "can_delete": item.owner_user_id == user.user_id,
                "chunk_count": len(repository.list_chunks(item.document_id)),
            }
            for item in items
        ]
