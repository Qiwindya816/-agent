"""Tests for executor context injection."""

from typing import Any

from multi_agent.executor import ToolExecutor
from schemas.agent_state import AgentState
from schemas.route import RouteResult
from schemas.tool import ToolResult
from tools.base import BaseTool
from tools.registry import ToolRegistry


class RecordingContextTool(BaseTool):
    name = "estimate_budget"
    description = "budget"

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self.calls = calls

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        self.calls.append(tool_input)
        return ToolResult.ok(self.name, "ok")


def test_executor_uses_context_builder_with_priority_and_budget() -> None:
    calls: list[dict[str, Any]] = []
    registry = ToolRegistry()
    registry.register(RecordingContextTool(calls))
    executor = ToolExecutor(registry)

    state = AgentState(user_id="user_a", session_id="session_a")
    executor.execute(
        RouteResult(intent="budget", tool_name="estimate_budget", confidence=0.9),
        "帮我规划成都三日行程",
        state,
    )

    context = calls[0]["contextual_input"]
    assert "用户本轮输入" in context
    assert "当前旅行约束" in context
