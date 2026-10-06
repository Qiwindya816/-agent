"""提供 Pydantic 结构化数据模型；本文件负责 `personalization` 相关实现。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RankingFeature(BaseModel):
    """承载 `RankingFeature` 对应的结构化结果及元数据。"""

    name: str
    value: float
    weight: float
    contribution: float
    explanation: str


class RankedActivity(BaseModel):
    """承载 `RankedActivity` 对应的结构化结果及元数据。"""

    activity_id: str | None = None
    name: str
    score: float
    rank: int
    features: list[RankingFeature] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    rejected_by_memory: bool = False
