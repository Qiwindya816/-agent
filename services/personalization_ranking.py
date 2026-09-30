"""Explainable ranking for activities using long-term memories and constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas.itinerary import Activity, Itinerary
from schemas.memory import RetrievedMemory
from schemas.personalization import RankingFeature, RankedActivity


@dataclass
class RankingWeights:
    preference_match: float = 0.30
    budget_match: float = 0.20
    popularity: float = 0.15
    freshness: float = 0.10
    diversity: float = 0.10
    verification: float = 0.10
    rejection_penalty: float = 0.35


class PersonalizationRankingService:
    """Rank candidate activities with explainable normalized features."""

    def __init__(self, weights: RankingWeights | None = None) -> None:
        self.weights = weights or RankingWeights()

    def rank(
        self,
        activities: list[Activity],
        *,
        memories: list[RetrievedMemory] | None = None,
        budget: float | None = None,
        existing_categories: list[str] | None = None,
    ) -> list[RankedActivity]:
        memories = memories or []
        ranked = [self._rank_activity(activity, memories, budget, existing_categories or []) for activity in activities]
        ranked.sort(key=lambda item: item.score, reverse=True)
        for index, item in enumerate(ranked, start=1):
            item.rank = index
        return ranked

    def _rank_activity(
        self,
        activity: Activity,
        memories: list[RetrievedMemory],
        budget: float | None,
        existing_categories: list[str],
    ) -> RankedActivity:
        features: list[RankingFeature] = []

        positive_statements = [memory.statement for memory in memories if memory.polarity == "positive"]
        negative_statements = [memory.statement for memory in memories if memory.polarity == "negative"]
        name = activity.name.lower()

        preference_match = 0.5
        matched_positive = [statement for statement in positive_statements if any(word in name for word in statement[2:])]
        if matched_positive:
            preference_match = 1.0
        features.append(self._feature("preference_match", preference_match, self.weights.preference_match, "长期偏好匹配度"))

        if budget is None:
            budget_match = 0.8
        elif activity.estimated_cost is None:
            budget_match = 0.6
        else:
            budget_match = 1.0 if activity.estimated_cost <= budget else 0.2
        features.append(self._feature("budget_match", budget_match, self.weights.budget_match, "预算匹配度"))

        popularity = 0.7
        if activity.poi and activity.poi.poi_id:
            popularity = 0.9
        features.append(self._feature("popularity", popularity, self.weights.popularity, "地点可信度与热度"))

        freshness = 1.0 if activity.verification_status == "verified" else 0.6
        features.append(self._feature("freshness", freshness, self.weights.freshness, "信息核验状态"))

        category = activity.category or "unknown"
        diversity = 0.4 if existing_categories and category in existing_categories else 1.0
        features.append(self._feature("diversity", diversity, self.weights.diversity, "类型多样性"))

        verification = 1.0 if activity.verification_status == "verified" else 0.5
        features.append(self._feature("verification", verification, self.weights.verification, "外部事实核验"))

        rejected_by_memory = any(self._matches_negative(activity, memory) for memory in memories if memory.polarity == "negative")
        score = sum(feature.contribution for feature in features)
        if rejected_by_memory:
            score -= self.weights.rejection_penalty

        reasons = [feature.explanation for feature in features if feature.contribution > 0]
        if rejected_by_memory:
            reasons.append("该活动命中用户历史拒绝记忆，已降权。")

        return RankedActivity(
            activity_id=activity.activity_id,
            name=activity.name,
            score=round(score, 4),
            rank=0,
            features=features,
            reasons=reasons,
            rejected_by_memory=rejected_by_memory,
        )

    def _matches_negative(self, activity: Activity, memory: RetrievedMemory) -> bool:
        structured = memory.structured_value or {}
        subject = str(structured.get("subject") or "").lower()
        return bool(subject and subject in activity.name.lower())

    @staticmethod
    def _feature(name: str, value: float, weight: float, explanation: str) -> RankingFeature:
        return RankingFeature(
            name=name,
            value=round(value, 4),
            weight=weight,
            contribution=round(value * weight, 4),
            explanation=explanation,
        )


def render_ranking_explanation(ranked_activities: list[RankedActivity]) -> str:
    """Render an explainable Markdown ranking summary for user-facing output."""
    if not ranked_activities:
        return "暂无可排序的候选活动。"
    lines = ["## 个性化排序说明"]
    for item in ranked_activities:
        lines.append(f"{item.rank}. {item.name}（{item.score:.3f} 分）")
        if item.rejected_by_memory:
            lines.append("  - 已根据历史拒绝记忆降权。")
        for feature in item.features:
            lines.append(f"  - {feature.explanation}：{feature.value:.2f} × {feature.weight:.2f} = {feature.contribution:.3f}")
    return "\n".join(lines)
