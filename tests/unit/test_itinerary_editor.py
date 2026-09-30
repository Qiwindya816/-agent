"""Tests for deterministic local itinerary editing."""

import pytest
from schemas.itinerary import Activity, Itinerary
from services.itinerary_editor import ItineraryEditor


def itinerary() -> Itinerary:
    return Itinerary.model_validate(
        {
            "travel_days": 1,
            "days": [
                {
                    "day": 1,
                    "activities": [
                        {"name": "故宫", "start_time": "09:00", "end_time": "12:00"},
                        {"name": "景山", "start_time": "13:00", "end_time": "15:00"},
                    ]
                }
            ]
        }
    )


def test_remove_activity_and_related_routes() -> None:
    trip = itinerary()
    first_id = trip.days[0].activities[0].activity_id
    from schemas.itinerary import RouteSegment

    trip.days[0].routes = [
        RouteSegment(
            origin_activity_id=first_id,
            destination_activity_id=trip.days[0].activities[1].activity_id,
            mode="walking",
        )
    ]

    edited = ItineraryEditor().remove_activity(trip, first_id)

    assert [activity.name for activity in edited.days[0].activities] == ["景山"]
    assert edited.days[0].routes == []


def test_update_activity_time_and_cost() -> None:
    trip = itinerary()
    activity_id = trip.days[0].activities[0].activity_id

    edited = ItineraryEditor().update_activity(trip, activity_id, start_time="10:00", estimated_cost=60)

    assert edited.days[0].activities[0].start_time == "10:00"
    assert edited.days[0].activities[0].estimated_cost == 60
    assert trip.days[0].activities[0].start_time == "09:00"


def test_reorder_activity_requires_all_ids() -> None:
    trip = itinerary()
    first_id = trip.days[0].activities[0].activity_id
    second_id = trip.days[0].activities[1].activity_id

    edited = ItineraryEditor().reorder_activities(trip, 1, [second_id, first_id])
    with pytest.raises(ValueError):
        ItineraryEditor().reorder_activities(trip, 1, [second_id, "missing"])
