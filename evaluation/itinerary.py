"""提供 离线评测数据、指标与报告；本文件负责 `itinerary` 相关实现。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from db.models import TripFeedback, TripPlanVersion
from schemas.itinerary import Itinerary
from validators.itinerary_validator import ItineraryValidator


def evaluate_itineraries(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """评估行程的时间冲突、预算和路线可行性。"""
    details: list[dict[str, Any]] = []
    conflict_count = budget_overrun_count = infeasible_route_count = 0
    for index, case in enumerate(cases, start=1):
        itinerary = Itinerary.model_validate(case.get("itinerary") or case)
        validation = ItineraryValidator().validate(itinerary)
        has_conflict = any("重叠" in error or "结束时间" in error for error in validation.errors)
        budget_limit = case.get("budget_limit")
        calculated_cost = max(
            sum(activity.estimated_cost or 0 for day in itinerary.days for activity in day.activities),
            sum(day.estimated_daily_cost or 0 for day in itinerary.days),
            itinerary.total_estimated_cost or 0,
        )
        budget_overrun = budget_limit is not None and calculated_cost > float(budget_limit)
        required_transitions = sum(max(0, len(day.activities) - 1) for day in itinerary.days)
        verified_routes = sum(
            1
            for day in itinerary.days
            for route in day.routes
            if route.verification_status == "verified" and route.duration_minutes is not None
        )
        route_infeasible = required_transitions > 0 and verified_routes < required_transitions
        conflict_count += int(has_conflict)
        budget_overrun_count += int(budget_overrun)
        infeasible_route_count += int(route_infeasible)
        details.append(
            {
                "id": case.get("id") or f"itinerary-{index}",
                "time_conflict": has_conflict,
                "budget_overrun": budget_overrun,
                "route_infeasible": route_infeasible,
                "calculated_cost": calculated_cost,
                "budget_limit": budget_limit,
                "errors": validation.errors,
                "warnings": validation.warnings,
            }
        )
    total = len(details)
    return {
        "case_count": total,
        "metrics": {
            "time_conflict_rate": round(conflict_count / total, 4) if total else 0.0,
            "budget_overrun_rate": round(budget_overrun_count / total, 4) if total else 0.0,
            "route_infeasible_rate": round(infeasible_route_count / total, 4) if total else 0.0,
        },
        "cases": details,
    }


def evaluate_trip_feedback(database: Any, *, user_id: str | None = None) -> dict[str, Any]:
    """汇总已持久化行程反馈中的接受和修改信号。"""
    with database.session() as session:
        feedback_query = select(TripFeedback.feedback_type, func.count()).group_by(TripFeedback.feedback_type)
        version_query = select(func.count()).select_from(TripPlanVersion)
        if user_id:
            feedback_query = feedback_query.where(TripFeedback.user_id == user_id)
            version_query = version_query.where(TripPlanVersion.user_id == user_id)
        counts = {name: count for name, count in session.execute(feedback_query)}
        version_count = int(session.scalar(version_query) or 0)
    decisions = counts.get("accept", 0) + counts.get("reject", 0)
    return {
        "version_count": version_count,
        "feedback_count": sum(counts.values()),
        "modification_count": counts.get("modify", 0),
        "acceptance_rate": round(counts.get("accept", 0) / decisions, 4) if decisions else None,
        "feedback_by_type": counts,
    }
