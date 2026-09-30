"""Deterministic local itinerary edits based on stable activity IDs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from schemas.itinerary import Activity, Itinerary


class ItineraryEditor:
    """Edit individual activities and route references without regenerating a trip."""

    def remove_activity(self, itinerary: Itinerary, activity_id: str) -> Itinerary:
        result = deepcopy(itinerary)
        for day in result.days:
            day.activities = [activity for activity in day.activities if activity.activity_id != activity_id]
            day.routes = [
                route
                for route in day.routes
                if activity_id not in {route.origin_activity_id, route.destination_activity_id}
            ]
        return result

    def replace_activity(self, itinerary: Itinerary, activity_id: str, replacement: Activity) -> Itinerary:
        result = deepcopy(itinerary)
        for day in result.days:
            day.activities = [
                replacement if activity.activity_id == activity_id else activity
                for activity in day.activities
            ]
        return result

    def update_activity(
        self,
        itinerary: Itinerary,
        activity_id: str,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        name: str | None = None,
        estimated_cost: float | None = None,
        notes: str | None = None,
    ) -> Itinerary:
        result = deepcopy(itinerary)
        for day in result.days:
            for index, activity in enumerate(day.activities):
                if activity.activity_id != activity_id:
                    continue
                updates: dict[str, Any] = {}
                if start_time is not None:
                    updates["start_time"] = start_time
                if end_time is not None:
                    updates["end_time"] = end_time
                if name is not None:
                    updates["name"] = name
                if estimated_cost is not None:
                    updates["estimated_cost"] = estimated_cost
                if notes is not None:
                    updates["notes"] = notes
                day.activities[index] = activity.model_copy(update=updates)
        return result

    def add_activity(self, itinerary: Itinerary, day_number: int, activity: Activity) -> Itinerary:
        result = deepcopy(itinerary)
        day = next((item for item in result.days if item.day == day_number), None)
        if day is None:
            raise ValueError(f"Day not found: {day_number}")
        day.activities.append(activity)
        return result

    def reorder_activities(self, itinerary: Itinerary, day_number: int, ordered_activity_ids: list[str]) -> Itinerary:
        result = deepcopy(itinerary)
        day = next((item for item in result.days if item.day == day_number), None)
        if day is None:
            raise ValueError(f"Day not found: {day_number}")
        by_id = {activity.activity_id: activity for activity in day.activities}
        missing = [activity_id for activity_id in ordered_activity_ids if activity_id not in by_id]
        if missing:
            raise ValueError(f"Activity IDs not found: {', '.join(missing)}")
        day.activities = [by_id[activity_id] for activity_id in ordered_activity_ids]
        return result
