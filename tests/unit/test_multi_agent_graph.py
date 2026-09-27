from typing import Any

from config.settings import get_settings
from multi_agent.graph import build_travel_graph
from multi_agent.summarizer import ResponseGenerator
from multi_agent.workflow import MultiAgentTravelWorkflow
from schemas.route import RoutePlan, RouteResult
from schemas.tool import ToolResult
from schemas.user_profile import ProfileExtraction, UserProfile


class FakeRouter:
    def route(self, user_input: str, state: Any) -> RoutePlan:
        return RoutePlan(
            steps=[
                RouteResult(
                    intent="weather",
                    tool_name="check_weather",
                    confidence=0.95,
                )
            ],
            confidence=0.95,
        )


class FakeExecutor:
    def execute_plan(self, plan: RoutePlan, user_input: str, state: Any, *, after_each: Any = None):
        route = plan.steps[0]
        result = ToolResult.ok(route.tool_name, "成都未来三天晴。", {"provider": "fake"})
        if after_each:
            after_each(route, result)
        return [(route, result)]


def fake_profile_extractor(*args: Any, **kwargs: Any) -> ProfileExtraction:
    return ProfileExtraction(profile_updates=UserProfile())


def test_five_agent_graph_executes_in_expected_order(tmp_path) -> None:
    settings = get_settings()
    old_dirs = (settings.memory_dir, settings.output_dir, settings.log_dir)
    settings.memory_dir = tmp_path / "memory"
    settings.output_dir = tmp_path / "outputs"
    settings.log_dir = tmp_path / "logs"
    try:
        graph = build_travel_graph(
            router=FakeRouter(),
            executor=FakeExecutor(),
            response_generator=ResponseGenerator(),
            profile_extractor=fake_profile_extractor,
        )
        workflow = MultiAgentTravelWorkflow(
            user_id="graph_user",
            session_id="session_graphtest",
            graph=graph,
        )

        result = workflow.run_with_state("查询成都天气")

        assert result["response"] == "成都未来三天晴。"
        assert result["node_trace"] == [
            "coordinator",
            "feedback",
            "planner",
            "tool_executor",
            "summarizer",
        ]
        assert result["tool_results"][0]["result"]["metadata"]["provider"] == "fake"
        assert result["errors"] == []
    finally:
        settings.memory_dir, settings.output_dir, settings.log_dir = old_dirs
