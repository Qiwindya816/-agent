"""Write policy for semantic, episodic, procedural, and explicit memories."""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import get_settings
from repositories.memory_repository import MemoryRepository
from schemas.memory import MemoryCandidate, MemoryWriteDecision


@dataclass
class MemoryPolicyResult:
    decision: MemoryWriteDecision
    existing_memory_id: str | None = None


class MemoryWritePolicy:
    """Decide whether a memory candidate should be created, merged, rejected, or deferred."""

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository
        self.settings = get_settings()

    def evaluate(self, candidate: MemoryCandidate) -> MemoryPolicyResult:
        existing = self.repository.find_similar_statements(
            candidate.user_id,
            candidate.statement,
            candidate.memory_type,
        )
        if existing:
            return MemoryPolicyResult(
                decision=MemoryWriteDecision(action="merge", memory_id=existing[0].memory_id, reason="相同陈述已有记忆，合并证据。"),
                existing_memory_id=existing[0].memory_id,
            )

        if candidate.memory_type == "explicit":
            return MemoryPolicyResult(
                decision=MemoryWriteDecision(action="create", reason="用户明确要求记住，允许直接写入。")
            )

        if candidate.memory_type == "episodic":
            return MemoryPolicyResult(
                decision=MemoryWriteDecision(action="create", reason="具体行为或反馈可保存为情景记忆。")
            )

        threshold = self._threshold(candidate.memory_type)
        if candidate.confidence < threshold:
            return MemoryPolicyResult(
                decision=MemoryWriteDecision(
                    action="defer",
                    reason=f"置信度低于阈值 {threshold}，先保留短期证据。",
                    required_evidence_count=self.settings.memory_min_evidence_count,
                )
            )

        return MemoryPolicyResult(
            decision=MemoryWriteDecision(
                action="create",
                reason=f"置信度达到阈值 {threshold}，允许写入长期记忆。",
                required_evidence_count=self.settings.memory_min_evidence_count,
            )
        )

    def _threshold(self, memory_type: str) -> float:
        if memory_type == "procedural":
            return self.settings.memory_procedural_write_threshold
        if memory_type == "semantic":
            return self.settings.memory_semantic_write_threshold
        return 0.85
