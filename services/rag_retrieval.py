"""提供 核心领域服务和外部服务适配；本文件负责 `rag_retrieval` 相关实现。"""

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
    """承载 `RetrievedChunk` 对应的结构化结果及元数据。"""

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
    source_authorization_status: str | None = None
    published_at: str | None = None
    fetched_at: str | None = None
    social_platform: str | None = None
    likes: int | None = None
    collects: int | None = None
    comments: int | None = None
    shares: int | None = None


class RagRetrievalService:
    """提供 `RagRetrievalService` 对应领域能力的统一服务。"""

    def __init__(
        self,
        database: DatabaseEngine | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """初始化 RagRetrievalService 及其运行依赖。"""
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
        """检索 `search` 对应的数据和流程，返回该步骤的处理结果。"""
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
                source_authorization_status=row["source_authorization_status"],
                published_at=str(row["published_at"]) if row.get("published_at") else None,
                fetched_at=str(row["fetched_at"]) if row.get("fetched_at") else None,
                social_platform=row.get("social_platform"),
                likes=row.get("likes"),
                collects=row.get("collects"),
                comments=row.get("comments"),
                shares=row.get("shares"),
            )
            for rank, (chunk_id, score) in enumerate(fused[:final_k], start=1)
            if (row := rows.get(chunk_id)) is not None
        ]

    def _dense(self, user_id: str, query_vector: list[float], top_k: int) -> list[str]:
        """按向量相似度召回候选知识切片。"""
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
        # PostgreSQL simple 解析器会把连续中文视作一个词，因此先拆出可能的检索词，
        # 并使用 ILIKE 子串匹配作为回退。
        """按全文关键词和子串匹配召回候选知识切片。"""
        tokens = self._search_tokens(query)
        token_query = " | ".join(tokens)
        like_tokens = tokens[:12] or [query]
        like_conditions = " or ".join(
            f"chunk_text ilike :like_{index}" for index in range(len(like_tokens))
        )
        match_score = " + ".join(
            f"case when chunk_text ilike :like_{index} then 1 else 0 end"
            for index in range(len(like_tokens))
        )
        sql = text(
            f"""
            select chunk_id
            from rag_chunks
            where (owner_user_id is null or owner_user_id = :user_id)
              and (
                tsv @@ to_tsquery('simple', :token_query)
                or chunk_text ilike :query
                or ({like_conditions})
              )
            order by ({match_score}) desc,
                     ts_rank(tsv, to_tsquery('simple', :token_query)) desc,
                     chunk_id
            limit :top_k
            """
        )
        params = {
            "user_id": user_id,
            "token_query": token_query,
            "query": f"%{query}%",
            "top_k": top_k,
            **{f"like_{index}": f"%{token}%" for index, token in enumerate(like_tokens)},
        }
        with self.database.session() as session:
            return [
                row[0]
                for row in session.execute(sql, params)
            ]

    @staticmethod
    def _search_tokens(query: str) -> list[str]:
        """检索 `_search_tokens` 对应的数据和流程，返回该步骤的处理结果。"""
        import re

        latin = re.findall(r"[A-Za-z0-9_]+", query)
        chinese_parts = re.findall(r"[\u4e00-\u9fff]+", query)
        travel_terms = (
            "公园", "自然", "湿地", "森林", "散步", "徒步", "美食", "老店", "本地人",
            "历史", "人文", "故宫", "博物馆", "艺术", "亲子", "夜景", "购物", "住宿",
            "拍照", "小众", "免费", "预约", "交通", "地铁",
        )
        tokens: list[str] = []
        # 中文旅行问题通常以城市或行政区开头。
        for part in chinese_parts:
            if len(part) >= 2:
                tokens.append(part[:2])
        tokens.extend(term for term in travel_terms if term in query)
        tokens.extend(latin)
        tokens.extend(part for part in chinese_parts if len(part) <= 8)
        return list(dict.fromkeys(token for token in tokens if token))[:24]

    def _geo(self, user_id: str, latitude: float, longitude: float, top_k: int) -> list[str]:
        """按经纬度距离召回附近知识切片。"""
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
        """按城市、主题、天数和受众召回行程模板。"""
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
        """加载chunks并返回符合当前作用域的结果。"""
        if not chunk_ids:
            return {}
        sql = text(
            """
            select c.chunk_id, c.document_id, c.owner_user_id, c.chunk_text, c.chunk_type,
                   c.city, c.theme, c.travel_days, c.audience,
                   s.name as source_name, coalesce(sn.canonical_url, s.url) as source_url,
                   s.authorization_status as source_authorization_status,
                   coalesce(sn.published_at, d.published_at) as published_at,
                   coalesce(sn.fetched_at, d.updated_at) as fetched_at,
                   sn.platform as social_platform,
                   metrics.likes, metrics.collects, metrics.comments, metrics.shares
            from rag_chunks c
            join rag_documents d on d.document_id = c.document_id
            join rag_sources s on s.source_id = d.source_id
            left join social_notes sn on sn.document_id = d.document_id
            left join lateral (
                select m.likes, m.collects, m.comments, m.shares
                from social_metric_snapshots m
                where m.social_note_id = sn.social_note_id
                order by m.captured_at desc
                limit 1
            ) metrics on true
            where c.chunk_id = any(:chunk_ids)
              and (c.owner_user_id is null or c.owner_user_id = :user_id)
            """
        )
        from sqlalchemy.orm import Session as OrmSession

        def load(session: OrmSession) -> dict[str, dict[str, object]]:
            """批量加载融合排名中的知识切片及来源元数据。"""
            return {
                row["chunk_id"]: dict(row._mapping)
                for row in session.execute(sql, {"chunk_ids": chunk_ids, "user_id": user_id})
            }

        with self.database.session() as session:
            result = session.execute(sql, {"chunk_ids": chunk_ids, "user_id": user_id})
            return {row._mapping["chunk_id"]: dict(row._mapping) for row in result}

    @staticmethod
    def _rrf(candidate_lists: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]:
        """使用 Reciprocal Rank Fusion 融合多路召回排名。"""
        scores: dict[str, float] = {}
        for candidates in candidate_lists:
            for rank, chunk_id in enumerate(candidates, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
