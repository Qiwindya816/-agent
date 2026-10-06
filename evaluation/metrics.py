"""提供 离线评测数据、指标与报告；本文件负责 `metrics` 相关实现。"""

from __future__ import annotations

import math


def precision_at_k(relevances: list[float], k: int) -> float:
    """计算前 K 个检索结果的二元精确率。"""
    if k <= 0:
        raise ValueError("k must be positive")
    return sum(1 for value in relevances[:k] if value > 0) / k


def recall_at_k(matched_relevant_items: int, total_relevant_items: int) -> float:
    """根据命中数和相关项总数计算 Recall@K。"""
    if total_relevant_items <= 0:
        return 0.0
    return min(matched_relevant_items, total_relevant_items) / total_relevant_items


def ndcg_at_k(relevances: list[float], ideal_relevances: list[float], k: int) -> float:
    """计算前 K 个结果的归一化折损累计增益。"""
    if k <= 0:
        raise ValueError("k must be positive")

    def dcg(values: list[float]) -> float:
        """计算给定相关性序列在 K 位置前的折损累计增益。"""
        return sum((2**value - 1) / math.log2(index + 2) for index, value in enumerate(values[:k]))

    ideal = dcg(sorted(ideal_relevances, reverse=True))
    return dcg(relevances) / ideal if ideal else 0.0
