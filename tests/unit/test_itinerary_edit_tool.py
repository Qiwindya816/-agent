"""Tests for the deterministic local itinerary edit tool."""

from typing import Any

from schemas.agent_state import AgentState
from schemas.itinerary import Itinerary
from schemas.route import RouteResult
from schemas.tool import ToolResult
from tools.itinerary_edit_tool import ItineraryEditTool


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
            ],
        }
    )


def state_with_itinerary() -> AgentState:
    state = AgentState(user_id="edit_user", session_id="session_edit")
    state.structured_itinerary = itinerary()
    return state


def test_edit_tool_updates_activity_without_rewriting_trip() -> None:
    state = state_with_itinerary()
    activity_id = state.structured_itinerary.days[0].activities[0].activity_id
    tool = ItineraryEditTool()

    result = tool.run(
        {
            "state": state,
            "mcp_arguments": {
                "action": "update",
                "activity_id": activity_id,
                "start_time": "10:00",
                "end_time": "13:00",
            },
        }
    )

    assert result.success is True
    edited = Itinerary.model_validate(result.data)
    assert edited.days[0].activities[0].start_time == "10:00"
    assert edited.days[0].activities[1].name == "景山"
    assert result.metadata["validation"]["is_valid"] is True


def test_edit_tool_rejects_unsupported_action() -> None:
    result = ItineraryEditTool().run(
        {
            "state": state_with_itinerary(),
            "mcp_arguments": {"action": "explode"},
        }
    )

    assert result.success is False
    assert result.error.code == "unsupported_action"


def test_registry_exposes_edit_tool() -> None:
    from tools.registry import build_default_registry

    assert "edit_itinerary_activity" in build_default_registry().list_tools()
