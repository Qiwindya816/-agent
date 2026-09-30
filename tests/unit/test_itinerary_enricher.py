"""Tests for normalized external tool outputs and itinerary enrichment."""

from typing import Any

from schemas.agent_state import AgentState
from schemas.itinerary import Itinerary
from schemas.route import RouteResult
from schemas.tool import ToolResult
from services.itinerary_enricher import ItineraryEnricher
from tools.base import BaseTool
from tools.registry import ToolRegistry

from multi_agent.executor import ToolExecutor


POI_RESPONSE = {
    "pois": [
        {
            "id": "B000A8UIN8",
            "name": "故宫博物院",
            "address": "景山前街4号",
            "cityname": "北京市",
            "adname": "东城区",
            "type": "旅游景点",
            "location": "116.397029,39.917839",
        }
    ]
}

ROUTE_RESPONSE = {
    "origin": "116.397463,39.909187",
    "destination": "116.397029,39.917839",
    "distance": "999",
    "transits": [
        {
            "duration": "1200",
            "walking_distance": "500",
            "segments": [
                {"bus": {"buslines": [{"name": "58路", "distance": "800", "duration": "600"}]}}
            ],
        }
    ],
}


def itinerary() -> Itinerary:
    return Itinerary.model_validate(
        {
            "title": "北京一日游",
            "destination": "北京",
            "days": [
                {
                    "day": 1,
                    "activities": [
                        {"name": "天安门", "verification_status": "unknown"},
                        {"name": "故宫博物院", "verification_status": "unknown"},
                    ]
                }
            ],
        }
    )


def test_poi_response_is_normalized() -> None:
    from schemas.tool_outputs import parse_poi_response

    pois = parse_poi_response(POI_RESPONSE)

    assert len(pois) == 1
    assert pois[0].name == "故宫博物院"
    assert pois[0].longitude == 116.397029
    assert pois[0].latitude == 39.917839
    assert pois[0].source.provider == "amap"


def test_route_response_is_normalized() -> None:
    from schemas.tool_outputs import parse_route_response

    route = parse_route_response(ROUTE_RESPONSE)

    assert route is not None
    assert route.distance_meters == 999
    assert route.duration_seconds == 1200
    assert route.steps[0].instruction == "58路"


def test_itinerary_enricher_attaches_verified_poi() -> None:
    enricher = ItineraryEnricher()
    result = ToolResult.ok("search_poi", POI_RESPONSE, {"provider": "amap"})

    enriched = enricher.enrich_from_poi(itinerary(), result)

    activity = enriched.days[0].activities[1]
    assert activity.verification_status == "verified"
    assert activity.poi is not None
    assert activity.poi.poi_id == "B000A8UIN8"
    assert activity.poi.location is not None
    assert activity.poi.location.longitude == 116.397029


def test_itinerary_enricher_attaches_route_between_matching_activities() -> None:
    enricher = ItineraryEnricher()
    trip = itinerary()
    trip.days[0].activities[0].poi = None
    # Use activity names in the route payload for matching.
    route_payload = dict(ROUTE_RESPONSE)
    route_payload["origin"] = "天安门,故宫博物院"
    result = ToolResult.ok("plan_route", route_payload, {"provider": "amap"})

    enriched = enricher.enrich_from_route(trip, result)

    assert len(enriched.days[0].routes) == 1
    segment = enriched.days[0].routes[0]
    assert segment.mode == "transit"
    assert segment.distance_meters == 999
    assert segment.verification_status == "verified"


def test_executor_enriches_itinerary_after_poi_tool() -> None:
    class PoiTool(BaseTool):
        name = "search_poi"
        description = "poi"

        def run(self, tool_input: dict[str, Any]) -> ToolResult:
            return ToolResult.ok(self.name, POI_RESPONSE, {"provider": "amap"})

    registry = ToolRegistry()
    registry.register(PoiTool())
    executor = ToolExecutor(registry)
    state = AgentState(user_id="user_a", session_id="session_a")
    state.structured_itinerary = itinerary()

    result = executor.execute(
        RouteResult(intent="poi", tool_name="search_poi", confidence=0.9),
        "搜索故宫",
        state,
    )

    assert result.success is True
    assert state.structured_itinerary.days[0].activities[1].verification_status == "verified"


def test_train_station_and_ticket_responses_are_normalized() -> None:
    from schemas.tool_outputs import parse_train_station_response, parse_train_ticket_response

    stations = parse_train_station_response(
        {"success": True, "stations": [{"name": "北京南", "code": "VNP", "pinyin": "beijingnan"}]}
    )
    tickets = parse_train_ticket_response(
        {
            "success": True,
            "trains": [
                {
                    "train_no": "G25",
                    "from_station": "北京南",
                    "from_station_code": "VNP",
                    "to_station": "上海虹桥",
                    "to_station_code": "AOH",
                    "start_time": "17:00",
                    "arrive_time": "21:18",
                    "duration": "04:18",
                    "seats": {"business": "13", "second_class": "有"},
                }
            ],
        }
    )

    assert stations[0].station_name == "北京南"
    assert stations[0].station_code == "VNP"
    assert tickets[0].train_no == "G25"
    assert tickets[0].seats[0].seat_class == "business"
    assert tickets[0].seats[0].value == "13"


def test_weather_markdown_is_normalized() -> None:
    from schemas.tool_outputs import parse_weather_markdown

    weather = parse_weather_markdown(
        "## 成都天气预报\n\n| 日期 | 天气 | 温度 | 降水 |\n|---|---|---:|---:|\n| 2026-09-30 | 小雨 | 18~24°C | 12 mm |"
    )

    assert weather is not None
    assert weather.location == "成都"
    assert weather.days[0].date == "2026-09-30"
    assert weather.days[0].min_temperature == 18
    assert weather.days[0].max_temperature == 24
    assert weather.days[0].precipitation == 12


def test_poi_detail_response_is_normalized() -> None:
    from schemas.tool_outputs import parse_poi_response

    detail = {
        "id": "B000A8UIN8",
        "name": "故宫博物院",
        "location": "116.397029,39.917839",
        "address": "景山前街4号",
        "city": "北京市",
        "type": "旅游景点",
        "rating": "4.9",
        "opentime2": "08:30-17:00",
    }

    pois = parse_poi_response(detail)

    assert pois[0].longitude == 116.397029
    assert pois[0].rating == 4.9
    assert pois[0].opening_hours == "08:30-17:00"


def test_train_tickets_are_added_as_verified_transport_options() -> None:
    from services.itinerary_enricher import ItineraryEnricher

    trip = itinerary()
    result = ToolResult.ok(
        "query_train_tickets",
        {
            "success": True,
            "trains": [
                {
                    "train_no": "G25",
                    "from_station": "北京南",
                    "to_station": "上海虹桥",
                    "start_time": "17:00",
                    "arrive_time": "21:18",
                    "duration": "04:18",
                    "seats": {"business": "13"},
                }
            ],
        },
        {"provider": "railway-12306"},
    )

    enriched = ItineraryEnricher().add_transport_options(trip, result, train_date="2026-10-01")

    option = enriched.transport_options[0]
    assert option.transport_type == "train"
    assert option.train_no == "G25"
    assert option.date == "2026-10-01"
    assert option.seats == {"business": "13"}
    assert option.verification_status == "verified"


def test_route_binding_honors_explicit_activity_ids() -> None:
    from services.itinerary_enricher import ItineraryEnricher

    trip = itinerary()
    origin_id = trip.days[0].activities[0].activity_id
    destination_id = trip.days[0].activities[1].activity_id
    route = RouteResult(
        intent="route",
        tool_name="plan_route",
        confidence=0.9,
        arguments={
            "origin": "116.397463,39.909187",
            "destination": "116.397029,39.917839",
            "origin_activity_id": origin_id,
            "destination_activity_id": destination_id,
            "city": "北京",
            "cityd": "北京",
        },
    )
    result = ToolResult.ok("plan_route", ROUTE_RESPONSE, {"provider": "amap"})

    enriched = ItineraryEnricher().enrich_from_route(trip, result, route=route)

    segment = enriched.days[0].routes[0]
    assert segment.origin_activity_id == origin_id
    assert segment.destination_activity_id == destination_id
