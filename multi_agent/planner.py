from typing import Any

from prompts.router_prompt import ROUTER_SYSTEM_PROMPT, build_router_prompt
from schemas.agent_state import AgentState
from schemas.route import RoutePlan, RouteResult
from services.llm_service import LLMService


SUPPORTED_TOOLS = {
    "recommend_destination",
    "plan_itinerary",
    "refine_itinerary",
    "estimate_budget",
    "check_weather",
    "convert_currency",
    "finalize_plan",
}


class TravelRouter:
    """把用户的一轮请求规划为一个或多个有序工具步骤。"""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        """初始化路由器；未传入服务时创建默认 LLM 服务。"""
        self.llm_service = llm_service or LLMService()

    def route(self, user_input: str, state: AgentState) -> RoutePlan:
        """优先使用 LLM 规划任务，输出不合法或调用失败时回退到规则规划。"""
        try:
            data = self.llm_service.generate_json(
                build_router_prompt(user_input, state),
                system_prompt=ROUTER_SYSTEM_PROMPT,
                temperature=0,
            )
            plan = self._parse_plan(data, state, user_input)
            if plan is not None:
                return plan
        except Exception:
            pass
        return self._route_with_rules(user_input, state)

    def _parse_plan(self, data: dict[str, Any], state: AgentState, user_input: str) -> RoutePlan | None:
        """校验模型工具名称、置信度和重复步骤，并兼容旧版单工具 JSON。"""
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            raw_steps = [data] if data.get("tool_name") else []

        steps: list[RouteResult] = []
        seen: set[str] = set()
        for raw in raw_steps[:7]:
            if not isinstance(raw, dict):
                continue
            tool_name = raw.get("tool_name")
            if tool_name not in SUPPORTED_TOOLS or tool_name in seen:
                continue
            seen.add(tool_name)
            confidence = _as_confidence(raw.get("confidence"), default=0.6)
            steps.append(
                RouteResult(
                    intent=str(raw.get("intent") or tool_name),
                    tool_name=tool_name,
                    reason=str(raw.get("reason") or ""),
                    confidence=confidence,
                    missing_fields=_string_list(raw.get("missing_fields")),
                    requires_existing_itinerary=bool(
                        raw.get("requires_existing_itinerary", tool_name == "refine_itinerary")
                    ),
                    depends_on=_string_list(raw.get("depends_on")),
                )
            )
        if not steps:
            return None
        steps = _normalize_step_order(steps)

        confidence = _as_confidence(
            data.get("confidence"),
            default=sum(step.confidence for step in steps) / len(steps),
        )
        missing_fields = _string_list(data.get("missing_fields"))
        needs_clarification = bool(data.get("needs_clarification")) or confidence < 0.45
        if any(step.tool_name == "refine_itinerary" for step in steps) and not state.current_itinerary:
            if not any(step.tool_name == "plan_itinerary" for step in steps):
                needs_clarification = True
                missing_fields = list(dict.fromkeys([*missing_fields, "current_itinerary"]))

        # 用户明确要求使用已有偏好且本地确实有记录时，不能仅因模型低置信度重复询问画像。
        if _requests_saved_preferences(user_input, state):
            blocking_fields = [field for field in missing_fields if field not in _PROFILE_FIELD_NAMES]
            if not blocking_fields:
                needs_clarification = False
                missing_fields = []

        question = data.get("clarification_question")
        if needs_clarification and not question:
            question = "我还不能确定你想完成什么任务，请补充目的地、旅行天数或希望我执行的操作。"
        return RoutePlan(
            steps=steps,
            confidence=confidence,
            missing_fields=missing_fields,
            needs_clarification=needs_clarification,
            clarification_question=str(question) if question else None,
        )

    def _route_with_rules(self, user_input: str, state: AgentState) -> RoutePlan:
        """使用关键词识别全部显式任务，并为规则结果给出可解释的置信度。"""
        text = user_input.lower()
        definitions = [
            ("recommend_destination", "destination_recommendation", ["recommend", "where", "destination", "推荐", "去哪"]),
            ("plan_itinerary", "itinerary_planning", ["plan", "itinerary", "行程", "规划", "安排", "攻略"]),
            ("refine_itinerary", "itinerary_refinement", ["too tired", "lighter", "relax", "第三天", "太累", "轻松", "修改", "调整", "优化"]),
            ("estimate_budget", "budget_estimation", ["budget", "cost", "price", "费用", "预算", "花费", "多少钱"]),
            ("check_weather", "weather_query", ["weather", "forecast", "天气", "气温", "下雨", "降雨", "预报"]),
            ("convert_currency", "currency_conversion", ["convert", "exchange", "currency", "汇率", "换算", "兑换"]),
            ("finalize_plan", "finalize_plan", ["export", "final", "download", "导出", "最终", "保存", "总结"]),
        ]
        steps = [
            RouteResult(intent=intent, tool_name=tool, reason="关键词规则识别到该任务。", confidence=0.82)
            for tool, intent, keywords in definitions
            if any(keyword in text for keyword in keywords)
        ]

        # “修改行程”只执行修改，不再额外把“行程”识别为新建任务。
        if any(step.tool_name == "refine_itinerary" for step in steps):
            steps = [step for step in steps if step.tool_name != "plan_itinerary"]
        if not steps:
            steps = [
                RouteResult(
                    intent="itinerary_planning",
                    tool_name="plan_itinerary",
                    reason="未识别到更明确的工具，默认按行程规划处理。",
                    confidence=0.55,
                )
            ]
        steps = _normalize_step_order(steps)

        needs_clarification = any(
            step.tool_name == "refine_itinerary" and not state.current_itinerary for step in steps
        )
        return RoutePlan(
            steps=steps,
            confidence=min(step.confidence for step in steps),
            missing_fields=["current_itinerary"] if needs_clarification else [],
            needs_clarification=needs_clarification,
            clarification_question="当前还没有可修改的行程。请先告诉我新的旅行需求，或让我先创建行程。"
            if needs_clarification
            else None,
        )


def _as_confidence(value: Any, *, default: float) -> float:
    """把模型置信度转换到 0-1 区间；无效值使用确定的默认值。"""
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    """仅保留列表中的非空字符串，避免模型异常类型进入路由模型。"""
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_step_order(steps: list[RouteResult]) -> list[RouteResult]:
    """修正模型常见依赖顺序：行程先于预算，最终汇总始终最后执行。"""
    order = {
        "recommend_destination": 10,
        "plan_itinerary": 20,
        "refine_itinerary": 20,
        "estimate_budget": 30,
        "check_weather": 40,
        "convert_currency": 50,
        "finalize_plan": 90,
    }
    normalized = sorted(steps, key=lambda step: order.get(step.tool_name, 60))
    itinerary_step = next(
        (step.tool_name for step in normalized if step.tool_name in {"plan_itinerary", "refine_itinerary"}),
        None,
    )
    if itinerary_step:
        for step in normalized:
            if step.tool_name == "estimate_budget" and itinerary_step not in step.depends_on:
                step.depends_on.append(itinerary_step)
    return normalized


_PROFILE_REFERENCE_WORDS = (
    "以前的长期偏好",
    "以前的偏好",
    "之前的偏好",
    "已有偏好",
    "我的偏好",
    "历史偏好",
    "saved preference",
    "previous preference",
)

_PROFILE_FIELD_NAMES = {
    "user_profile",
    "preferences",
    "长期偏好",
    "用户偏好",
    "历史偏好",
    "以前的偏好",
    "interests",
    "travel_style",
    "avoid",
    "accommodation_preference",
    "food_preference",
    "transport_preference",
    "dietary_restrictions",
    "mobility_constraints",
    "visited_destinations",
}


def _requests_saved_preferences(user_input: str, state: AgentState) -> bool:
    """判断本轮是否引用了已有偏好，并确认长期画像中存在至少一个有效值。"""
    prompt_text = user_input.lower()
    references_profile = any(word in prompt_text for word in _PROFILE_REFERENCE_WORDS)
    profile_values = state.user_profile.model_dump(exclude_none=True).values()
    has_saved_profile = any(value not in (None, "", []) for value in profile_values)
    return references_profile and has_saved_profile
