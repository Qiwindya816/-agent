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
