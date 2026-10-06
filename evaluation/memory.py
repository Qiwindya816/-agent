"""提供 离线评测数据、指标与报告；本文件负责 `memory` 相关实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from db.models import MemoryItem
from repositories.memory_repository import MemoryRepository
from schemas.memory import RetrievedMemory
from services.memory_conflict_resolver import MemoryConflictResolver


def evaluate_memory_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """根据人工记忆用例评估冲突消解结果。"""
    details = []
    wrong_selected = selected_total = correct_conflicts = conflict_total = 0
    for index, case in enumerate(cases, start=1):
        memories = [_memory_from_dict(item) for item in case.get("memories", [])]
        decisions = MemoryConflictResolver().resolve(memories, scope=case.get("scope"))
        selected = [decision.memory.memory_id for decision in decisions]
        expected = [str(item) for item in case.get("expected_selected", [])]
        expected_first = case.get("expected_first")
        forbidden = {str(item) for item in case.get("forbidden_selected", [])}
        errors = len([item for item in selected if item in forbidden])
        selected_total += len(selected)
        wrong_selected += errors
        is_conflict_case = bool(expected or forbidden)
        correct = (
            all(item in selected for item in expected)
            and not errors
            and (expected_first is None or (selected and selected[0] == str(expected_first)))
        )
        conflict_total += int(is_conflict_case)
        correct_conflicts += int(is_conflict_case and correct)
        details.append(
            {
                "id": case.get("id") or f"memory-{index}",
                "selected": selected,
                "expected_selected": expected,
                "expected_first": expected_first,
                "forbidden_selected": sorted(forbidden),
                "passed": correct,
            }
        )
    return {
        "case_count": len(details),
        "metrics": {
            "wrong_retrieval_rate": round(wrong_selected / selected_total, 4) if selected_total else 0.0,
            "conflict_resolution_accuracy": round(correct_conflicts / conflict_total, 4) if conflict_total else 0.0,
        },
        "cases": details,
    }


def evaluate_memory_privacy(database: Any) -> dict[str, Any]:
    """检查所有持久化记忆是否遵守用户所有权边界。"""
    checked = leaks = 0
    with database.session() as session:
        repository = MemoryRepository(session)
        items = list(session.scalars(select(MemoryItem)))
        for item in items:
            checked += 1
            outsider = f"eval_outsider_{item.user_id}"
            if repository.get_item(outsider, item.memory_id) is not None:
                leaks += 1
    return {
        "checked_items": checked,
        "privacy_leak_count": leaks,
        "privacy_pass_rate": round((checked - leaks) / checked, 4) if checked else 1.0,
    }


def _memory_from_dict(data: dict[str, Any]) -> RetrievedMemory:
    """将评测用字典转换为结构化记忆对象。"""
    payload = dict(data)
    for field in ("first_observed_at", "last_confirmed_at", "expires_at"):
        if isinstance(payload.get(field), str):
            payload[field] = datetime.fromisoformat(payload[field])
    return RetrievedMemory.model_validate(payload)
