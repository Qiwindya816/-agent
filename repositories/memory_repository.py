"""Repository for long-term memory items, evidence, and vector backfill."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import uuid4

from db.base import utc_now
from db.models import MemoryEvidence, MemoryItem, User
from schemas.memory import MemoryCandidate, RetrievedMemory


class MemoryRepository:
    """CRUD and evidence operations for long-term memory."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_item(self, candidate: MemoryCandidate, embedding: list[float] | None = None) -> MemoryItem:
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
            evidence_count=1,
            source_type="explicit" if candidate.evidence_type == "explicit_statement" else "inferred",
            embedding=embedding,
            embedding_text=candidate.statement,
        )
        self.session.add(item)
        self.session.flush()
        self.add_evidence(item.memory_id, candidate)
        item.evidence_count = 1
        return item

    def get_item(self, user_id: str, memory_id: str) -> MemoryItem | None:
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
        status: str = "active",
    ) -> list[MemoryItem]:
        statement = select(MemoryItem).where(MemoryItem.user_id == user_id, MemoryItem.status == status)
        if memory_type:
            statement = statement.where(MemoryItem.memory_type == memory_type)
        if scope:
            statement = statement.where(MemoryItem.scope == scope)
        return list(self.session.scalars(statement.order_by(MemoryItem.last_confirmed_at.desc())))

    def find_similar_statements(self, user_id: str, statement: str, memory_type: str) -> list[MemoryItem]:
        # Deterministic exact-match merging. Vector similarity is used at retrieval.
        normalized = statement.strip().lower()
        return [
            item
            for item in self.list_items(user_id, memory_type=memory_type)
            if item.statement.strip().lower() == normalized
        ]

    def add_evidence(self, memory_id: str, candidate: MemoryCandidate) -> MemoryEvidence:
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
        if item.evidence_count <= 1:
            item.evidence_count = 1
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def update_statement(self, user_id: str, memory_id: str, statement: str) -> MemoryItem | None:
        item = self.get_item(user_id, memory_id)
        if item is None:
            return None
        item.statement = statement
        item.embedding_text = statement
        item.embedding = None
        self.session.flush()
        return item

    def list_evidence(self, user_id: str, memory_id: str) -> list[MemoryEvidence]:
        """List evidence for a memory while enforcing user ownership."""
        item = self.get_item(user_id, memory_id)
        if item is None:
            return []
        return sorted(item.evidence, key=lambda evidence: evidence.observed_at)

    def clear_items(self, user_id: str) -> int:
        """Delete all active long-term memories and evidence for one user."""
        items = self.list_items(user_id, status="active")
        for item in items:
            self.session.delete(item)
        self.session.flush()
        return len(items)

    def export_items(self, user_id: str) -> list[dict]:
        """Export a user's memories and evidence for data portability."""
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
        item = self.get_item(user_id, memory_id)
        if item is None:
            return False
        self.session.delete(item)
        self.session.flush()
        return True

    @staticmethod
    def to_retrieved(item: MemoryItem, similarity: float = 0.0) -> RetrievedMemory:
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
