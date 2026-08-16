from typing import Any

from agent.router import TravelRouter
from schemas.agent_state import AgentState


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

