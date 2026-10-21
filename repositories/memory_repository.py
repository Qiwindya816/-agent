"""提供 带用户隔离的数据访问；本文件负责 `memory_repository` 相关实现。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import uuid4

from db.base import utc_now
from db.models import MemoryEvidence, MemoryItem, User
from schemas.memory import MemoryCandidate, RetrievedMemory


class MemoryRepository:
    """封装 `MemoryRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:  # 数据库会话
        """初始化 MemoryRepository 及其运行依赖。"""
        self.session = session

    def create_item(
        self,
        candidate: MemoryCandidate,
        embedding: list[float] | None = None,
        *,
        status: str = "active",
    ) -> MemoryItem:
        """创建记录，并保持相关状态或持久化数据一致。"""
        user = self.session.get(User, candidate.user_id)
        if user is None:
            user = User(user_id=candidate.user_id)
            self.session.add(user)
            self.session.flush()
        item = MemoryItem(
            memory_id=f"memory_{uuid4().hex[:16]}",
            user_id=candidate.user_id,
            memory_type=candidate.memory_type,
            category=candidate.category,
            statement=candidate.statement,
            structured_value=candidate.structured_value,
            scope=candidate.scope,
            polarity=candidate.polarity,
            importance=candidate.importance,
            confidence=candidate.confidence,
            evidence_count=0,
            source_type="explicit" if candidate.evidence_type == "explicit_statement" else "inferred",
            status=status,
            embedding=embedding,
            embedding_text=candidate.statement,
        )
        self.session.add(item)
        self.session.flush()
        self.add_evidence(item.memory_id, candidate)
        return item

    def get_item(self, user_id: str, memory_id: str) -> MemoryItem | None:
        """获取记录并返回符合当前作用域的结果。"""
        item = self.session.get(MemoryItem, memory_id)
        if item is None or item.user_id != user_id:
            return None
        return item

    def list_items(
        self,
        user_id: str,
        *,
        memory_type: str | None = None,
        scope: str | None = None,
        status: str | None = "active",
    ) -> list[MemoryItem]:
        """列出记录列表并返回符合当前作用域的结果。"""
        statement = select(MemoryItem).where(MemoryItem.user_id == user_id)
        if status is not None:
            statement = statement.where(MemoryItem.status == status)
        if memory_type:
            statement = statement.where(MemoryItem.memory_type == memory_type)
        if scope:
            statement = statement.where(MemoryItem.scope == scope)
        return list(self.session.scalars(statement.order_by(MemoryItem.last_confirmed_at.desc())))

    def find_similar_statements(
        self,
        user_id: str,
        statement: str,
        memory_type: str,
        *,
        polarity: str | None = None,
        scope: str | None = None,
    ) -> list[MemoryItem]:
        """查找同类型、同倾向且文本相同或高度近似的已有记忆。"""
        normalized = self._normalize_statement(statement)
        canonical = self._canonical_statement(statement)
        return [
            item
            for item in self.list_items(user_id, memory_type=memory_type, status=None)
            if item.status in {"active", "pending"}
            if polarity is None or item.polarity == polarity
            if scope is None or item.scope == scope
            if self._is_similar_statement(item.statement, normalized, canonical)
        ]

    @staticmethod
    def _normalize_statement(statement: str) -> str:
        return re.sub(r"\s+", "", statement.strip().lower())

    @classmethod
    def _canonical_statement(cls, statement: str) -> str:
        normalized = cls._normalize_statement(statement)
        for marker in ("用户", "本人", "我", "非常", "很", "比较", "偏好", "喜欢", "希望", "参观"):
            normalized = normalized.replace(marker, "")
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)

    @classmethod
    def _is_similar_statement(cls, existing: str, normalized: str, canonical: str) -> bool:
        existing_normalized = cls._normalize_statement(existing)
        if existing_normalized == normalized:
            return True
        existing_canonical = cls._canonical_statement(existing)
        if min(len(existing_canonical), len(canonical)) >= 3 and (
            existing_canonical in canonical or canonical in existing_canonical
        ):
            return True
        return SequenceMatcher(None, existing_normalized, normalized).ratio() >= 0.9

    def add_evidence(self, memory_id: str, candidate: MemoryCandidate) -> MemoryEvidence:
        """添加证据，并保持相关状态或持久化数据一致。"""
        item = self.session.get(MemoryItem, memory_id)
        if item is None or item.user_id != candidate.user_id:
            raise LookupError("Memory not found for user")
        evidence = MemoryEvidence(
            evidence_id=f"evidence_{uuid4().hex[:16]}",
            memory_id=memory_id,
            user_id=candidate.user_id,
            session_id=candidate.session_id,
            message_id=candidate.message_id,
            trip_id=candidate.trip_id,
            evidence_text=candidate.evidence_text,
            evidence_type=candidate.evidence_type,
            confidence=candidate.confidence,
        )
        item.evidence_count += 1
        item.last_confirmed_at = utc_now()
        item.confidence = max(item.confidence, candidate.confidence)
        item.importance = max(item.importance, candidate.importance)
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def update_statement(
        self,
        user_id: str,
        memory_id: str,
        statement: str,
        *,
        embedding: list[float] | None = None,
    ) -> MemoryItem | None:
        """更新陈述，并保持相关状态或持久化数据一致。"""
        item = self.get_item(user_id, memory_id)
        if item is None:
            return None
        item.statement = statement
        item.embedding_text = statement
        item.embedding = embedding
        self.session.flush()
        return item

    def list_evidence(self, user_id: str, memory_id: str) -> list[MemoryEvidence]:
        """列出 `list_evidence` 对应的数据和流程，返回该步骤的处理结果。"""
        item = self.get_item(user_id, memory_id)
        if item is None:
            return []
        return sorted(item.evidence, key=lambda evidence: evidence.observed_at)

    def clear_items(self, user_id: str) -> int:
        """清空 `clear_items` 对应的数据和流程，返回该步骤的处理结果。"""
        items = self.list_items(user_id, status=None)
        for item in items:
            self.session.delete(item)
        self.session.flush()
        return len(items)

    def activate_item(self, user_id: str, memory_id: str) -> MemoryItem | None:
        """把累计到足够证据的候选记忆晋升为可召回的长期记忆。"""
        item = self.get_item(user_id, memory_id)
        if item is None:
            return None
        item.status = "active"
        item.last_confirmed_at = utc_now()
        self.session.flush()
        return item

    def export_items(self, user_id: str) -> list[dict]:
        """导出 `export_items` 对应的数据和流程，返回该步骤的处理结果。"""
        result = []
        for item in self.list_items(user_id):
            result.append(
                {
                    "memory_id": item.memory_id,
                    "memory_type": item.memory_type,
                    "category": item.category,
                    "statement": item.statement,
                    "structured_value": item.structured_value,
                    "scope": item.scope,
                    "polarity": item.polarity,
                    "importance": item.importance,
                    "confidence": item.confidence,
                    "evidence_count": item.evidence_count,
                    "status": item.status,
                    "first_observed_at": item.first_observed_at.isoformat() if item.first_observed_at else None,
                    "last_confirmed_at": item.last_confirmed_at.isoformat() if item.last_confirmed_at else None,
                    "expires_at": item.expires_at.isoformat() if item.expires_at else None,
                    "evidence": [
                        {
                            "evidence_id": evidence.evidence_id,
                            "session_id": evidence.session_id,
                            "message_id": evidence.message_id,
                            "trip_id": evidence.trip_id,
                            "evidence_text": evidence.evidence_text,
                            "evidence_type": evidence.evidence_type,
                            "confidence": evidence.confidence,
                            "observed_at": evidence.observed_at.isoformat() if evidence.observed_at else None,
                        }
                        for evidence in item.evidence
                    ],
                }
            )
        return result

    def delete_item(self, user_id: str, memory_id: str) -> bool:
        """删除记录，并保持相关状态或持久化数据一致。"""
        item = self.get_item(user_id, memory_id)
        if item is None:
            return False
        self.session.delete(item)
        self.session.flush()
        return True

    @staticmethod
    def to_retrieved(item: MemoryItem, similarity: float = 0.0) -> RetrievedMemory:
        """转换为retrieved，供后续流程使用。"""
        return RetrievedMemory(
            memory_id=item.memory_id,
            user_id=item.user_id,
            memory_type=item.memory_type,  # type: ignore[arg-type]
            category=item.category,
            statement=item.statement,
            structured_value=item.structured_value,
            scope=item.scope,
            polarity=item.polarity,
            importance=item.importance,
            confidence=item.confidence,
            evidence_count=item.evidence_count,
            status=item.status,
            first_observed_at=item.first_observed_at,
            last_confirmed_at=item.last_confirmed_at,
            expires_at=item.expires_at,
            similarity=similarity,
        )
