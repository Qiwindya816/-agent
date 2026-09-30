from typing import Any

from multi_agent.planner import TravelRouter
from prompts.router_prompt import build_router_prompt
from schemas.agent_state import AgentState
from schemas.user_profile import UserProfile


class FakeLLM:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.response = response or {}
        self.error = error

    def generate_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if self.error:
            raise self.error
        return self.response


def test_router_returns_confident_multi_step_plan() -> None:
    router = TravelRouter(
        FakeLLM(
            {
                "steps": [
                    {"intent": "plan", "tool_name": "plan_itinerary", "confidence": 0.94},
                    {
                        "intent": "budget",
                        "tool_name": "estimate_budget",
                        "confidence": 0.9,
                        "depends_on": ["plan_itinerary"],
                    },
                ],
                "confidence": 0.91,
            }
        )
    )

    plan = router.route("规划成都行程并估算预算", AgentState())

    assert [step.tool_name for step in plan.steps] == ["plan_itinerary", "estimate_budget"]
    assert plan.confidence == 0.91
    assert all(step.confidence is not None for step in plan.steps)


def test_rule_fallback_detects_multiple_tasks() -> None:
    router = TravelRouter(FakeLLM(error=RuntimeError("offline")))

    plan = router.route("规划成都三日行程，估算预算并查询天气", AgentState())

    assert [step.tool_name for step in plan.steps] == [
        "plan_itinerary",
        "estimate_budget",
        "check_weather",
    ]
    assert 0 <= plan.confidence <= 1


def test_saved_preferences_are_visible_and_do_not_trigger_redundant_question() -> None:
    response = {
        "steps": [{"intent": "plan", "tool_name": "plan_itinerary", "confidence": 0.35}],
        "confidence": 0.35,
        "missing_fields": ["preferences"],
        "needs_clarification": True,
        "clarification_question": "请提供以前的偏好。",
    }
    state = AgentState(user_profile=UserProfile(interests=["历史文化"]))
    router = TravelRouter(FakeLLM(response))
    user_input = "请根据我以前的长期偏好规划西安3日行程"

    plan = router.route(user_input, state)

    assert '"历史文化"' in build_router_prompt(user_input, state)
    assert plan.needs_clarification is False
    assert plan.missing_fields == []


def test_missing_saved_preferences_still_triggers_question() -> None:
    response = {
        "steps": [{"intent": "plan", "tool_name": "plan_itinerary", "confidence": 0.35}],
        "confidence": 0.35,
        "missing_fields": ["preferences"],
        "needs_clarification": True,
    }

    plan = TravelRouter(FakeLLM(response)).route(
        "请根据我以前的长期偏好规划西安3日行程",
        AgentState(),
    )

    assert plan.needs_clarification is True



def test_rule_fallback_adds_geocode_before_route_for_place_names() -> None:
    router = TravelRouter(FakeLLM(error=RuntimeError("offline")))
    router.supported_tools = router.supported_tools | {"geocode", "plan_route"}

    plan = router.route("查询从北京天安门到故宫的公交路线", AgentState())

    assert [step.tool_name for step in plan.steps] == ["geocode", "plan_route"]
    assert plan.steps[-1].depends_on == ["geocode"]


def test_router_ignores_numeric_dependency_indexes() -> None:
    response = {
        "steps": [
            {"intent": "geocode", "tool_name": "geocode", "confidence": 0.9},
            {
                "intent": "route",
                "tool_name": "plan_route",
                "confidence": 0.9,
                "depends_on": ["0", "1"],
            },
        ],
        "confidence": 0.9,
    }
    router = TravelRouter(FakeLLM(response))
    router.supported_tools = router.supported_tools | {"geocode", "plan_route"}

    plan = router.route("查询从北京天安门到北京南站的公交路线", AgentState())

    route_step = next(step for step in plan.steps if step.tool_name == "plan_route")
    assert "0" not in route_step.depends_on
    assert "1" not in route_step.depends_on


def test_rule_fallback_detects_train_ticket_query() -> None:
    router = TravelRouter(FakeLLM(error=RuntimeError("offline")))
    router.supported_tools = router.supported_tools | {"query_train_tickets"}

    plan = router.route("查询2026-09-30从北京到上海的火车票", AgentState())

    assert [step.tool_name for step in plan.steps] == ["query_train_tickets"]
