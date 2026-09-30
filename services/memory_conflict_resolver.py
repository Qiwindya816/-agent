"""Resolve conflicts between current context and retrieved long-term memories."""

from __future__ import annotations

from typing import Any

from schemas.memory import MemoryDecision, RetrievedMemory


TYPE_PRIORITY = {
    "explicit": 100,
    "semantic": 80,
    "procedural": 70,
    "episodic": 60,
}


class MemoryConflictResolver:
    """Rank memories while respecting recency, confidence, scope, and current context."""

    def resolve(
        self,
        memories: list[RetrievedMemory],
        current_context: Any | None = None,
        *,
        scope: str | None = None,
    ) -> list[MemoryDecision]:
        decisions: list[MemoryDecision] = []
        for memory in memories:
            priority = self._priority(memory, scope)
            reason = self._reason(memory)
            decisions.append(MemoryDecision(memory=memory, priority=priority, reason=reason))

        return sorted(decisions, key=lambda item: item.priority, reverse=True)[:5]

    @staticmethod
    def _priority(memory: RetrievedMemory, scope: str | None) -> float:
        priority = TYPE_PRIORITY.get(memory.memory_type, 50)
        priority += memory.confidence * 5
        priority += memory.importance * 3
        if scope and memory.scope == scope:
            priority += 10
        elif scope and memory.scope != "global":
            priority -= 5
        if memory.last_confirmed_at is not None:
            priority += 1
        return priority

    @staticmethod
    def _reason(memory: RetrievedMemory) -> str:
        return (
            f"{memory.memory_type} 记忆，置信度 {memory.confidence:.2f}，"
            f"证据数 {memory.evidence_count}，作用域 {memory.scope}。"
        )
