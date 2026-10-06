"""提供 核心领域服务和外部服务适配；本文件负责 `memory_conflict_resolver` 相关实现。"""

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
    """集中实现 `MemoryConflictResolver` 对应的确定性业务逻辑。"""

    def resolve(
        self,
        memories: list[RetrievedMemory],
        current_context: Any | None = None,
        *,
        scope: str | None = None,
    ) -> list[MemoryDecision]:
        """按类型、置信度、重要性和作用域选择优先记忆。"""
        decisions: list[MemoryDecision] = []
        for memory in memories:
            priority = self._priority(memory, scope)
            reason = self._reason(memory)
            decisions.append(MemoryDecision(memory=memory, priority=priority, reason=reason))

        return sorted(decisions, key=lambda item: item.priority, reverse=True)[:5]

    @staticmethod
    def _priority(memory: RetrievedMemory, scope: str | None) -> float:
        """计算一条记忆在冲突消解中的综合优先级。"""
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
        """生成人类可读的记忆选择原因。"""
        return (
            f"{memory.memory_type} 记忆，置信度 {memory.confidence:.2f}，"
            f"证据数 {memory.evidence_count}，作用域 {memory.scope}。"
        )
