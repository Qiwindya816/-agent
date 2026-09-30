"""End-to-end PostgreSQL checkpoint persistence test using injected fakes."""

from typing import Any

from config.settings import get_settings
from multi_agent.graph import build_travel_graph
from multi_agent.summarizer import ResponseGenerator
from schemas.route import RoutePlan, RouteResult
from schemas.tool import ToolResult
from schemas.user_profile import ProfileExtraction, UserProfile


class FakeRouter:
    def route(self, user_input: str, state: Any) -> RoutePlan:
        return RoutePlan(
            steps=[RouteResult(intent="weather", tool_name="check_weather", confidence=0.95)],
            confidence=0.95,
        )


class FakeExecutor:
    def execute_plan(self, plan: RoutePlan, user_input: str, state: Any, *, after_each: Any = None):
        route = plan.steps[0]
        result = ToolResult.ok(route.tool_name, "checkpoint ok", {"provider": "fake"})
        if after_each:
            after_each(route, result)
        return [(route, result)]


def fake_profile_extractor(*args: Any, **kwargs: Any) -> ProfileExtraction:
    return ProfileExtraction(profile_updates=UserProfile())


def test_postgresql_graph_checkpoint_can_be_restored() -> None:
    settings = get_settings()
    old_dirs = (settings.memory_dir, settings.output_dir, settings.log_dir)
    settings.memory_dir = "memory_data_checkpoint_test"
    settings.output_dir = "outputs_checkpoint_test"
    settings.log_dir = "logs_checkpoint_test"
    try:
        graph = build_travel_graph(
            router=FakeRouter(),
            executor=FakeExecutor(),
            response_generator=ResponseGenerator(),
            profile_extractor=fake_profile_extractor,
        )
        result = graph.invoke(
            {
                "user_id": "checkpoint_test_user",
                "session_id": "session_checkpoint_integration",
                "user_input": "测试",
                "node_trace": [],
                "errors": [],
            },
            config={"configurable": {"thread_id": "session_checkpoint_integration"}},
        )

        restored = graph.get_state(config={"configurable": {"thread_id": "session_checkpoint_integration"}})

        assert result["response"] == "checkpoint ok"
        assert restored.next == ()
        assert restored.values["response"] == "checkpoint ok"
        assert restored.values["node_trace"] == [
            "coordinator",
            "feedback",
            "planner",
            "tool_executor",
            "summarizer",
        ]
    finally:
        settings.memory_dir, settings.output_dir, settings.log_dir = old_dirs
