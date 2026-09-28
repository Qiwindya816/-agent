from typing import Any

from schemas.itinerary import Itinerary
from services.itinerary_renderer import render_itinerary_markdown
from tools.itinerary_plan_tool import ItineraryPlanTool


class FakeStructuredLLM:
    def generate_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "title": "成都两日慢游",
            "departure_city": "上海",
            "destination": "成都",
            "travel_days": 1,
            "days": [
                {
                    "day": 1,
                    "theme": "老城",
                    "activities": [
                        {
                            "name": "人民公园",
                            "start_time": "09:00",
                            "verification_status": "unknown",
                        }
                    ],
                }
            ],
            "assumptions": ["具体营业时间等待地图服务核验"],
        }


def test_itinerary_tool_returns_validated_structured_data() -> None:
    result = ItineraryPlanTool(FakeStructuredLLM()).run({"user_input": "规划成都两日游"})

    assert result.success is True
    assert result.metadata == {"schema": "Itinerary", "schema_version": "3.0"}
    itinerary = Itinerary.model_validate(result.data)
    assert itinerary.destination == "成都"
    assert itinerary.days[0].activities[0].activity_id.startswith("activity_")
    assert itinerary.days[0].activities[0].verification_status == "unknown"


def test_structured_itinerary_has_deterministic_markdown_view() -> None:
    itinerary = Itinerary.model_validate(FakeStructuredLLM().generate_json())

    rendered = render_itinerary_markdown(itinerary)

    assert "# 成都两日慢游" in rendered
    assert "## 第 1 天 · 老城" in rendered
    assert "人民公园" in rendered
    assert "具体营业时间等待地图服务核验" in rendered
