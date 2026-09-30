from typing import Any

from multi_agent.executor import ToolExecutor
from schemas.agent_state import AgentState
from schemas.route import RoutePlan, RouteResult
from schemas.tool import ToolResult
from tools.base import BaseTool
from tools.registry import ToolRegistry


class RecordingTool(BaseTool):
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self.description = name
        self.calls = calls

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        self.calls.append(self.name)
        return ToolResult.ok(self.name, self.name)


def test_executor_runs_plan_in_order_and_honors_dependencies() -> None:
    calls: list[str] = []
    registry = ToolRegistry()
    registry.register(RecordingTool("plan_itinerary", calls))
    registry.register(RecordingTool("estimate_budget", calls))
    executor = ToolExecutor(registry)
    plan = RoutePlan(
        steps=[
            RouteResult(intent="plan", tool_name="plan_itinerary", confidence=0.9),
            RouteResult(
                intent="budget",
                tool_name="estimate_budget",
                confidence=0.9,
                depends_on=["plan_itinerary"],
            ),
        ],
        confidence=0.9,
    )

    results = executor.execute_plan(plan, "规划并估算", AgentState())

    assert calls == ["plan_itinerary", "estimate_budget"]
    assert all(result.success for _, result in results)


class GeocodeRouteRecordingTool(BaseTool):
    def __init__(self, name: str, calls: list[dict[str, Any]]) -> None:
        self.name = name
        self.description = name
        self.calls = calls

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        self.calls.append(tool_input["mcp_arguments"])
        if self.name == "geocode":
            return ToolResult.ok(
                self.name,
                {
                    "results": [
                        {"address": "北京天安门", "location": "116.397463,39.909187", "city": "北京"},
                        {"address": "故宫", "location": "116.397428,39.90923", "city": "北京"},
                    ]
                },
                {"provider": "mcp"},
            )
        return ToolResult.ok(self.name, {"distance": "1411"})


def test_executor_backfills_geocode_results_into_route_arguments() -> None:
    calls: list[dict[str, Any]] = []
    registry = ToolRegistry()
    registry.register(GeocodeRouteRecordingTool("geocode", calls))
    registry.register(GeocodeRouteRecordingTool("plan_route", calls))
    executor = ToolExecutor(registry)
    plan = RoutePlan(
        steps=[
            RouteResult(
                intent="geocoding",
                tool_name="geocode",
                confidence=0.9,
                arguments={"addresses": ["北京天安门", "故宫"]},
            ),
            RouteResult(
                intent="route",
                tool_name="plan_route",
                confidence=0.9,
                depends_on=["geocode"],
            ),
        ],
        confidence=0.9,
    )

    results = executor.execute_plan(plan, "查询从北京天安门到故宫的公交路线", AgentState())

    assert all(result.success for _, result in results)
    assert calls[0]["addresses"] == ["北京天安门", "故宫"]
    assert calls[1] == {
        "origin": "116.397463,39.909187",
        "destination": "116.397428,39.90923",
        "city": "北京",
        "cityd": "北京",
    }
