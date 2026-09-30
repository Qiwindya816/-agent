"""Tests for explainable personalized activity ranking."""

from schemas.itinerary import Activity
from schemas.memory import RetrievedMemory
from schemas.personalization import RankedActivity
from services.personalization_ranking import PersonalizationRankingService


def memory(**kwargs):
    values = {
        "memory_id": "memory_1",
        "user_id": "user_a",
        "memory_type": "episodic",
        "category": "rejected_action",
        "statement": "用户拒绝夜爬长城",
        "structured_value": {"subject": "夜爬长城", "action": "rejected"},
        "scope": "trip",
        "polarity": "negative",
        "importance": 0.8,
        "confidence": 0.95,
        "evidence_count": 1,
        "status": "active",
    }
    values.update(kwargs)
    return RetrievedMemory(**values)


def test_ranking_explains_preference_budget_and_rejection() -> None:
    service = PersonalizationRankingService()
    museum = Activity(name="故宫博物院", category="museum", estimated_cost=60)
    night_wall = Activity(name="夜爬长城", category="outdoor", estimated_cost=100)

    ranked = service.rank([night_wall, museum], memories=[memory()], budget=80)

    assert ranked[0].name == "故宫博物院"
    assert ranked[0].rank == 1
    assert ranked[-1].rejected_by_memory is True
    assert any(feature.name == "preference_match" for feature in ranked[0].features)
    assert any("历史拒绝记忆" in reason for reason in ranked[-1].reasons)


def test_ranking_penalizes_duplicate_categories_for_diversity() -> None:
    service = PersonalizationRankingService()
    museum = Activity(name="博物馆A", category="museum")
    park = Activity(name="公园B", category="park")

    ranked = service.rank([museum, park], existing_categories=["museum"])

    diversity_by_name = {
        ranked_activity.name: next(feature.value for feature in ranked_activity.features if feature.name == "diversity")
        for ranked_activity in ranked
    }
    assert diversity_by_name["公园B"] > diversity_by_name["博物馆A"]
