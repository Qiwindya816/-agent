"""Hybrid RAG retrieval with BM25, vector, geographic, and template recall."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings
from db.engine import DatabaseEngine, get_database_engine
from services.embedding_service import EmbeddingService


@dataclass
class RetrievedChunk:
    """A fused RAG candidate with provenance."""

    chunk_id: str
    document_id: str
    owner_user_id: str | None
    chunk_text: str
    chunk_type: str
    score: float
    rank: int
    city: str | None = None
    theme: str | None = None
    travel_days: int | None = None
    audience: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    fetched_at: str | None = None


class RagRetrievalService:
    """Run multi-way recall and Reciprocal Rank Fusion on rag_chunks."""

    def __init__(
        self,
        database: DatabaseEngine | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.database = database or get_database_engine()
        self.embedding_service = embedding_service
        self.settings = get_settings()

    def search(
        self,
        user_id: str,
        query: str,
        *,
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        theme: str | None = None,
        travel_days: int | None = None,
        audience: str | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Return public and current-user chunks ordered by RRF score."""
        settings = self.settings
        final_k = top_k or settings.rag_rrf_top_k
        dense_ids: list[str] = []
        if self.embedding_service is not None and not self.database.url.startswith("sqlite"):
            query_vector = self.embedding_service.embed_query(query)
            dense_ids = self._dense(user_id, query_vector, settings.rag_dense_top_k)
        bm25_ids = (
            []
            if self.database.url.startswith("sqlite")
            else self._bm25(user_id, query, settings.rag_bm25_top_k)
        )
        geo_ids = self._geo(user_id, latitude, longitude, settings.rag_geo_top_k) if latitude is not None and longitude is not None else []
        template_ids = self._templates(
            user_id,
            city,
            theme,
            travel_days,
            audience,
            settings.rag_template_top_k,
        )
        fused = self._rrf([dense_ids, bm25_ids, geo_ids, template_ids])
        if not fused:
            return []
        limited = [chunk_id for chunk_id, _ in fused[:final_k]]
        rows = self._load_chunks(user_id, limited)
        return [
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                owner_user_id=row["owner_user_id"],
                chunk_text=row["chunk_text"],
                chunk_type=row["chunk_type"],
                score=score,
                rank=rank,
                city=row["city"],
                theme=row["theme"],
                travel_days=row["travel_days"],
                audience=row["audience"],
                source_name=row["source_name"],
                source_url=row["source_url"],
                fetched_at=str(row["fetched_at"]) if row.get("fetched_at") else None,
            )
            for rank, (chunk_id, score) in enumerate(fused[:final_k], start=1)
            if (row := rows.get(chunk_id)) is not None
        ]

    def _dense(self, user_id: str, query_vector: list[float], top_k: int) -> list[str]:
        vector_text = "[" + ",".join(str(value) for value in query_vector) + "]"
        sql = text(
            """
            select chunk_id
            from rag_chunks
            where (owner_user_id is null or owner_user_id = :user_id)
              and embedding is not null
            order by embedding <=> cast(:vector as vector)
            limit :top_k
            """
        )
        with self.database.session() as session:
            return [row[0] for row in session.execute(sql, {"user_id": user_id, "vector": vector_text, "top_k": top_k})]

    def _bm25(self, user_id: str, query: str, top_k: int) -> list[str]:
        # PostgreSQL simple parser treats contiguous Chinese as one token. Split
        # the query into likely searchable tokens and fall back to substring ILIKE.
        tokens = self._search_tokens(query)
        token_query = " | ".join(tokens)
        sql = text(
            """
            select chunk_id
            from rag_chunks
            where (owner_user_id is null or owner_user_id = :user_id)
              and (
                tsv @@ to_tsquery('simple', :token_query)
                or chunk_text ilike :query
                or :token1 ilike '%' || chunk_text || '%'
                or chunk_text ilike '%' || :token1 || '%'
                or chunk_text ilike '%' || :token2 || '%'
              )
            order by ts_rank(tsv, to_tsquery('simple', :token_query)) desc, chunk_id
            limit :top_k
            """
        )
        tokens = self._search_tokens(query)
        token1 = tokens[0] if tokens else query
        token2 = tokens[1] if len(tokens) > 1 else token1
        with self.database.session() as session:
            return [
                row[0]
                for row in session.execute(
                    sql,
                    {
                        "user_id": user_id,
                        "token_query": token_query,
                        "query": f"%{query}%",
                        "token1": token1,
                        "token2": token2,
                        "top_k": top_k,
                    },
                )
            ]

    @staticmethod
    def _search_tokens(query: str) -> list[str]:
        """Split Chinese and Latin words into safe tsquery tokens."""
        import re

        return [token for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", query) if token]

    def _geo(self, user_id: str, latitude: float, longitude: float, top_k: int) -> list[str]:
        sql = text(
            """
            select chunk_id
            from rag_chunks
            where (owner_user_id is null or owner_user_id = :user_id)
              and latitude is not null and longitude is not null
            order by ((latitude - :latitude) ^ 2 + (longitude - :longitude) ^ 2)
            limit :top_k
            """
        )
        with self.database.session() as session:
            return [row[0] for row in session.execute(sql, {"user_id": user_id, "latitude": latitude, "longitude": longitude, "top_k": top_k})]

    def _templates(
        self,
        user_id: str,
        city: str | None,
        theme: str | None,
        travel_days: int | None,
        audience: str | None,
        top_k: int,
    ) -> list[str]:
        if not any([city, theme, travel_days, audience]):
            return []
        conditions = ["chunk_type = 'template'", "(owner_user_id is null or owner_user_id = :user_id)"]
        params: dict[str, Any] = {"user_id": user_id, "top_k": top_k}
        if city:
            conditions.append("city = :city")
            params["city"] = city
        if theme:
            conditions.append("theme = :theme")
            params["theme"] = theme
        if travel_days:
            conditions.append("travel_days = :travel_days")
            params["travel_days"] = travel_days
        if audience:
            conditions.append("audience = :audience")
            params["audience"] = audience
        sql = text(f"select chunk_id from rag_chunks where {' and '.join(conditions)} limit :top_k")
        with self.database.session() as session:
            return [row[0] for row in session.execute(sql, params)]

    def _load_chunks(self, user_id: str, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not chunk_ids:
            return {}
        sql = text(
            """
            select c.chunk_id, c.document_id, c.owner_user_id, c.chunk_text, c.chunk_type,
                   c.city, c.theme, c.travel_days, c.audience,
                   s.name as source_name, s.url as source_url, d.updated_at as fetched_at
            from rag_chunks c
            join rag_documents d on d.document_id = c.document_id
            join rag_sources s on s.source_id = d.source_id
            where c.chunk_id = any(:chunk_ids)
              and (c.owner_user_id is null or c.owner_user_id = :user_id)
            """
        )
        from sqlalchemy.orm import Session as OrmSession

        def load(session: OrmSession) -> dict[str, dict[str, object]]:
            return {
                row["chunk_id"]: dict(row._mapping)
                for row in session.execute(sql, {"chunk_ids": chunk_ids, "user_id": user_id})
            }

        with self.database.session() as session:
            result = session.execute(sql, {"chunk_ids": chunk_ids, "user_id": user_id})
            return {row._mapping["chunk_id"]: dict(row._mapping) for row in result}

    @staticmethod
    def _rrf(candidate_lists: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]:
        scores: dict[str, float] = {}
        for candidates in candidate_lists:
            for rank, chunk_id in enumerate(candidates, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
