"""Tests for deterministic itinerary validation."""

from schemas.itinerary import Activity, Itinerary
from validators.itinerary_validator import ItineraryValidator


def test_validator_detects_time_overlap_and_invalid_end_time() -> None:
    itinerary = Itinerary.model_validate(
        {
            "travel_days": 1,
            "days": [
                {
                    "day": 1,
                    "activities": [
                        {"name": "A", "start_time": "09:00", "end_time": "10:30"},
                        {"name": "B", "start_time": "10:00", "end_time": "09:30"},
                    ]
                }
            ]
        }
    )

    result = ItineraryValidator().validate(itinerary)

    assert not result.is_valid
    assert any("时间重叠" in error for error in result.errors)
    assert any("结束时间早于或等于开始时间" in error for error in result.errors)


def test_validator_detects_over_budget_and_high_intensity() -> None:
    activities = [
        {"name": f"活动{i}", "start_time": f"{9 + i}:00", "end_time": f"{9 + i}:59", "estimated_cost": 100}
        for i in range(6)
    ]
    itinerary = Itinerary.model_validate(
        {
            "travel_days": 1,
            "total_estimated_cost": 100,
            "days": [
                {
                    "day": 1,
                    "activities": activities,
                    "estimated_daily_cost": 600,
                }
            ],
        }
    )

    result = ItineraryValidator().validate(itinerary)

    assert result.is_valid
    assert any("节奏可能过紧" in warning for warning in result.warnings)
    assert any("超过总预算" in warning for warning in result.warnings)


def test_validator_detects_unverified_route_and_activity() -> None:
    itinerary = Itinerary.model_validate(
        {
            "travel_days": 1,
            "days": [
                {
                    "day": 1,
                    "activities": [
                        {"name": "A", "start_time": "09:00", "end_time": "10:00"},
                        {"name": "B", "start_time": "10:30", "end_time": "11:30"},
                    ],
                    "routes": [
                        {
                            "origin_activity_id": "not_exists",
                            "destination_activity_id": "also_missing",
                            "mode": "transit",
                            "verification_status": "unknown",
                        }
                    ],
                }
            ],
        }
    )

    result = ItineraryValidator().validate(itinerary)

    assert not result.is_valid
    assert any("引用了不存在的活动" in error for error in result.errors)
    assert any("尚未核验" in warning for warning in result.warnings)
