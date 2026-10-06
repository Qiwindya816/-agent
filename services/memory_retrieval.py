"""提供 核心领域服务和外部服务适配；本文件负责 `memory_retrieval` 相关实现。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from config.settings import get_settings
from db.engine import DatabaseEngine, get_database_engine
from repositories.memory_repository import MemoryRepository
from schemas.memory import RetrievedMemory
from services.embedding_service import EmbeddingService


class MemoryRetrievalService:
    """提供 `MemoryRetrievalService` 对应领域能力的统一服务。"""

    def __init__(
        self,
        database: DatabaseEngine | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """初始化 MemoryRetrievalService 及其运行依赖。"""
        self.database = database or get_database_engine()
        self.embedding_service = embedding_service
        self.settings = get_settings()

    def retrieve(
        self,
        user_id: str,
        query: str,
        *,
        scope: str | None = None,
        memory_types: list[str] | None = None,
    ) -> list[RetrievedMemory]:
        """按用户、语义相关性、类型和作用域召回长期记忆。"""
        if self.embedding_service is None or self.database.url.startswith("sqlite"):
            return self._metadata_retrieval(user_id, query, scope, memory_types)

        query_vector = self.embedding_service.embed_query(query)
        vector_text = "[" + ",".join(str(value) for value in query_vector) + "]"
        sql = text(
            """
            select memory_id, 1 - (embedding <=> cast(:vector as vector)) as similarity
            from memory_items
            where user_id = :user_id
              and status = 'active'
              and embedding is not null
            order by embedding <=> cast(:vector as vector)
            limit :top_k
            """
        )
        with self.database.session() as session:
            rows = session.execute(sql, {"user_id": user_id, "vector": vector_text, "top_k": self.settings.memory_retrieval_top_k}).mappings().all()
            repository = MemoryRepository(session)
            results = []
            for row in rows:
                item = repository.get_item(user_id, row["memory_id"])
                if item is None:
                    continue
                if memory_types and item.memory_type not in memory_types:
                    continue
                if scope and item.scope != scope:
                    continue
                similarity = float(row["similarity"])
                if similarity < self.settings.memory_min_relevance:
                    continue
                results.append(MemoryRepository.to_retrieved(item, similarity))
            return results

    def _metadata_retrieval(
        self,
        user_id: str,
        query: str,
        scope: str | None,
        memory_types: list[str] | None,
    ) -> list[RetrievedMemory]:
        """处理 `_metadata_retrieval` 对应的数据和流程，返回该步骤的处理结果。"""
        normalized_query = query.lower()
        with self.database.session() as session:
            repository = MemoryRepository(session)
            items = repository.list_items(user_id, scope=scope)
            matched = [
                MemoryRepository.to_retrieved(item, 1.0 if any(word in item.statement.lower() for word in normalized_query.split()) else 0.0)
                for item in items
                if (not memory_types or item.memory_type in memory_types)
                and any(word in item.statement.lower() for word in normalized_query.split())
            ]
            return matched[: self.settings.memory_retrieval_top_k]
