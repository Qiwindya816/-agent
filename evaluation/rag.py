"""提供 离线评测数据、指标与报告；本文件负责 `rag` 相关实现。"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from evaluation.metrics import ndcg_at_k, precision_at_k, recall_at_k


def _value(item: Any, name: str, default: Any = None) -> Any:
    """统一读取字典或对象形式检索结果中的字段。"""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _gold_rules(case: dict[str, Any]) -> list[dict[str, Any]]:
    """读取当前或旧版格式的金集相关性规则。"""
    rules = case.get("relevant")
    if isinstance(rules, list) and rules:
        return [rule for rule in rules if isinstance(rule, dict)]
    legacy = case.get("expected_chunk_text_contains")
    if isinstance(legacy, list) and legacy:
        return [{"contains_all": legacy, "relevance": 1}]
    return []


def _matches(item: Any, rule: dict[str, Any]) -> bool:
    """判断一个检索结果是否满足指定金集规则。"""
    exact_fields = ("chunk_id", "document_id", "source_name", "source_url")
    for field in exact_fields:
        if rule.get(field) is not None and str(_value(item, field, "")) != str(rule[field]):
            return False
    text = str(_value(item, "chunk_text", ""))
    if any(str(token) not in text for token in rule.get("contains_all", [])):
        return False
    contains_any = [str(token) for token in rule.get("contains_any", [])]
    if contains_any and not any(token in text for token in contains_any):
        return False
    return True


def evaluate_rag_cases(
    retrieval: Any,
    cases: list[dict[str, Any]],
    *,
    default_user_id: str,
    k: int = 5,
) -> dict[str, Any]:
    """执行 RAG 检索用例并返回宏观指标和可审计明细。"""
    details: list[dict[str, Any]] = []
    for case in cases:
        top_k = int(case.get("k") or k)
        rules = _gold_rules(case)
        results = retrieval.search(
            str(case.get("user_id") or default_user_id),
            str(case["query"]),
            top_k=top_k,
            **dict(case.get("filters") or {}),
        )
        matched_rule_indexes: set[int] = set()
        relevances: list[float] = []
        result_rows: list[dict[str, Any]] = []
        for item in results[:top_k]:
            matches = [index for index, rule in enumerate(rules) if _matches(item, rule)]
            matched_rule_indexes.update(matches)
            grade = max((float(rules[index].get("relevance", 1)) for index in matches), default=0.0)
            relevances.append(grade)
            row = asdict(item) if is_dataclass(item) else dict(item) if isinstance(item, dict) else {
                key: _value(item, key)
                for key in (
                    "rank", "chunk_id", "document_id", "chunk_text", "source_name", "source_url",
                    "source_authorization_status", "published_at", "fetched_at",
                )
            }
            row["relevance"] = grade
            result_rows.append(row)

        # 关键词规则可能匹配多个相关文档。理想序列同时纳入已观察到的相关文档
        # 和未命中的金集规则，确保 nDCG 始终处于 [0, 1]。
        ideal = [value for value in relevances if value > 0]
        ideal.extend(
            float(rule.get("relevance", 1))
            for index, rule in enumerate(rules)
            if index not in matched_rule_indexes
        )
        traceable = [
            item
            for item in results[:top_k]
            if _value(item, "document_id")
            and _value(item, "source_name")
            and _value(item, "source_url")
            and _value(item, "fetched_at")
            and _value(item, "source_authorization_status")
        ]
        relevant_traceable = [item for item in traceable if any(_matches(item, rule) for rule in rules)]
        metrics = {
            f"recall@{top_k}": recall_at_k(len(matched_rule_indexes), len(rules)),
            f"precision@{top_k}": precision_at_k(relevances, top_k),
            f"ndcg@{top_k}": ndcg_at_k(relevances, ideal, top_k),
            "citation_accuracy": len(relevant_traceable) / len(traceable) if traceable else 0.0,
            "source_traceability": len(traceable) / len(results[:top_k]) if results[:top_k] else 0.0,
        }
        details.append(
            {
                "id": case.get("id"),
                "query": case["query"],
                "gold_count": len(rules),
                "matched_gold_count": len(matched_rule_indexes),
                "metrics": metrics,
                "passed": bool(rules) and len(matched_rule_indexes) == len(rules),
                "results": result_rows,
            }
        )

    metric_names = sorted({name for detail in details for name in detail["metrics"]})
    macro = {
        name: round(sum(detail["metrics"].get(name, 0.0) for detail in details) / len(details), 4)
        for name in metric_names
    } if details else {}
    return {
        "case_count": len(details),
        "passed_cases": sum(1 for detail in details if detail["passed"]),
        "macro_metrics": macro,
        "cases": details,
    }
