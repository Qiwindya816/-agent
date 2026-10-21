"""提供 核心领域服务和外部服务适配；本文件负责 `memory_conflict_resolver` 相关实现。"""

from __future__ import annotations

import re
from typing import Any

from config.settings import get_settings
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

        ranked = sorted(decisions, key=lambda item: item.priority, reverse=True)
        selected: list[MemoryDecision] = []
        current_polarity = self._context_polarity(current_context)
        current_key = self._canonical(str(current_context or ""))
        for decision in ranked:
            memory = decision.memory
            key = self._canonical(memory.statement)
            if (
                current_polarity
                and key
                and key in current_key
                and memory.polarity in {"positive", "negative"}
                and memory.polarity != current_polarity
            ):
                # 本轮明确要求永远高于历史记忆。
                continue

            conflict = next(
                (
                    existing
                    for existing in selected
                    if self._conflicts(existing.memory, memory)
                ),
                None,
            )
            if conflict is not None:
                decision.suppressed_by = conflict.memory.memory_id
                continue
            selected.append(decision)

        return selected[: get_settings().memory_injection_top_k]

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

    @classmethod
    def _conflicts(cls, left: RetrievedMemory, right: RetrievedMemory) -> bool:
        """识别同一主题上正负倾向相反的记忆，保留排序更高的一条。"""
        if left.polarity not in {"positive", "negative"} or right.polarity not in {"positive", "negative"}:
            return False
        if left.polarity == right.polarity:
            return False
        if left.scope != right.scope and "global" not in {left.scope, right.scope}:
            return False
        left_key = cls._canonical(left.statement)
        right_key = cls._canonical(right.statement)
        return bool(left_key and right_key and (left_key in right_key or right_key in left_key))

    @staticmethod
    def _canonical(text: str) -> str:
        normalized = text.lower()
        for marker in ("用户", "本人", "我", "不喜欢", "不要", "避免", "讨厌", "喜欢", "偏好", "希望", "请记住"):
            normalized = normalized.replace(marker, "")
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)

    @staticmethod
    def _context_polarity(context: Any | None) -> str | None:
        text = str(context or "")
        if any(marker in text for marker in ("不喜欢", "不要", "避免", "讨厌")):
            return "negative"
        if any(marker in text for marker in ("喜欢", "希望", "想要")):
            return "positive"
        return None
