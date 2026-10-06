"""提供 核心领域服务和外部服务适配；本文件负责 `memory_write_policy` 相关实现。"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import get_settings
from repositories.memory_repository import MemoryRepository
from schemas.memory import MemoryCandidate, MemoryWriteDecision


@dataclass
class MemoryPolicyResult:
    """承载 记忆、策略 的结构化结果。"""
    decision: MemoryWriteDecision
    existing_memory_id: str | None = None


class MemoryWritePolicy:
    """封装 `MemoryWritePolicy` 的核心数据与行为。"""

    def __init__(self, repository: MemoryRepository) -> None:
        """初始化 MemoryWritePolicy 及其运行依赖。"""
        self.repository = repository
        self.settings = get_settings()

    def evaluate(self, candidate: MemoryCandidate) -> MemoryPolicyResult:
        """评估候选记忆应创建、合并、延迟还是拒绝。"""
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
        """返回指定记忆类型对应的写入置信度阈值。"""
        if memory_type == "procedural":
            return self.settings.memory_procedural_write_threshold
        if memory_type == "semantic":
            return self.settings.memory_semantic_write_threshold
        return 0.85
