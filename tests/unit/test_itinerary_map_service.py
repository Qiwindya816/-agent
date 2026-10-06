from schemas.agent_state import AgentState
from schemas.itinerary import Itinerary
from schemas.tool import ToolResult
from services.itinerary_map_service import ItineraryMapService


class FakeGeocodeTool:
    def run(self, tool_input):
        addresses = tool_input["mcp_arguments"]["addresses"]
        return ToolResult.ok(
            "geocode",
            {"results": [{"address": addresses[0], "location": "116.397029,39.917839"}]},
            {"provider": "mcp"},
        )


def test_map_service_attaches_coordinates_and_skips_meals() -> None:
    itinerary = Itinerary.model_validate(
        {
            "destination": "北京",
            "days": [
                {
                    "day": 1,
                    "activities": [
                        {"name": "故宫博物院参观（需预约）"},
                        {"name": "午餐与休息"},
                    ],
                }
            ],
        }
    )

    enriched, result, resolved = ItineraryMapService().enrich(itinerary, FakeGeocodeTool(), AgentState())

    assert result.success is True
    assert resolved == 1
    assert enriched.days[0].activities[0].poi.location.longitude == 116.397029
    assert enriched.days[0].activities[1].poi is None
