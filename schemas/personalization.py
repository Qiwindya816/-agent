"""提供 Pydantic 结构化数据模型；本文件负责 `personalization` 相关实现。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RankingFeature(BaseModel):
    """承载 `RankingFeature` 对应的结构化结果及元数据。"""

    name: str  # 特征名
    value: float  # 归一化值
    weight: float  # 权重
    contribution: float  # 加权贡献
    explanation: str  # 解释


class RankedActivity(BaseModel):
    """承载 `RankedActivity` 对应的结构化结果及元数据。"""

    activity_id: str | None = None  # 活动 ID
    name: str  # 活动名
    score: float  # 综合得分
    rank: int  # 排名
    features: list[RankingFeature] = Field(default_factory=list)  # 评分特征
    reasons: list[str] = Field(default_factory=list)  # 推荐理由
    rejected_by_memory: bool = False  # 是否被历史拒绝记忆降权
