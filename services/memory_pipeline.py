"""Extract, validate, and persist long-term memory candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from db.engine import DatabaseEngine, get_database_engine
from repositories.memory_repository import MemoryRepository
from schemas.memory import MemoryCandidate, MemoryWriteDecision
from services.embedding_service import EmbeddingService
from services.memory_write_policy import MemoryPolicyResult, MemoryWritePolicy


ALLOWED_MEMORY_TYPES = {"semantic", "episodic", "procedural", "explicit"}
SENSITIVE_MARKERS = ("身份证", "护照", "银行卡", "密码", "病历", "过敏")


@dataclass
class MemoryPipelineResult:
    """Summary of one memory ingestion batch."""

    created: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class MemoryPipeline:
    """Convert raw extraction output into memory candidates and persist valid items."""

    def __init__(
        self,
        database: DatabaseEngine | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.database = database or get_database_engine()
        self.embedding_service = embedding_service

    def ingest_candidates(
        self,
        raw_candidates: list[dict[str, Any]],
        *,
        user_id: str,
        session_id: str | None = None,
        trip_id: str | None = None,
        message_id: str | None = None,
    ) -> MemoryPipelineResult:
        result = MemoryPipelineResult()
        if not raw_candidates:
            return result
        if not self._memory_enabled(user_id):
            result.rejected.append("long_term_memory_disabled")
            return result

        candidates = self.parse_candidates(
            raw_candidates,
            user_id=user_id,
            session_id=session_id,
            trip_id=trip_id,
            message_id=message_id,
        )
        if not candidates:
            result.rejected.append("no_valid_candidate")
            return result

        with self.database.session() as session:
            repository = MemoryRepository(session)
            policy = MemoryWritePolicy(repository)
            for candidate in candidates:
                if self._is_sensitive(candidate):
                    result.rejected.append(candidate.statement)
                    continue
                policy_result = policy.evaluate(candidate)
                action = policy_result.decision.action
                if action == "merge" and policy_result.existing_memory_id:
                    repository.add_evidence(policy_result.existing_memory_id, candidate)
                    result.merged.append(policy_result.existing_memory_id)
                elif action == "create":
                    embedding = self._embedding(candidate.statement)
                    item = repository.create_item(candidate, embedding=embedding)
                    result.created.append(item.memory_id)
                elif action == "defer":
                    result.deferred.append(candidate.statement)
                else:
                    result.rejected.append(candidate.statement)
        return result

    def parse_candidates(
        self,
        raw_candidates: list[dict[str, Any]],
        *,
        user_id: str,
        session_id: str | None,
        trip_id: str | None,
        message_id: str | None,
    ) -> list[MemoryCandidate]:
        parsed: list[MemoryCandidate] = []
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            data = dict(raw)
            data.update(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "trip_id": trip_id,
                    "message_id": message_id,
                }
            )
            if data.get("memory_type") not in ALLOWED_MEMORY_TYPES:
                continue
            try:
                parsed.append(MemoryCandidate.model_validate(data))
            except ValidationError:
                continue
        return parsed

    def _embedding(self, statement: str) -> list[float] | None:
        if self.embedding_service is None:
            return None
        try:
            return self.embedding_service.embed_query(statement)
        except Exception:
            return None

    @staticmethod
    def _is_sensitive(candidate: MemoryCandidate) -> bool:
        text = f"{candidate.statement}\n{candidate.evidence_text}"
        return any(marker in text for marker in SENSITIVE_MARKERS)

    def _memory_enabled(self, user_id: str) -> bool:
        from db.models import User

        try:
            with self.database.session() as session:
                user = session.get(User, user_id)
                return bool(user is None or user.long_term_memory_enabled)
        except Exception:
            return False
