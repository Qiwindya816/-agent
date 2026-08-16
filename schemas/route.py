from pydantic import BaseModel, Field


TOOL_STAGE_MAP = {
    "recommend_destination": "recommending_destination",
    "plan_itinerary": "planning_itinerary",
    "refine_itinerary": "refining_itinerary",
    "estimate_budget": "estimating_budget",
    "check_weather": "checking_weather",
    "convert_currency": "converting_currency",
    "finalize_plan": "finalizing_plan",
}


class RouteResult(BaseModel):
    """一个可执行的工具步骤。"""

    intent: str
    tool_name: str
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    requires_existing_itinerary: bool = False
    depends_on: list[str] = Field(default_factory=list)

    @property
    def stage(self) -> str:
        """根据工具名称返回对应的 Agent 工作阶段。"""
        return TOOL_STAGE_MAP.get(self.tool_name, "collecting_preferences")


class RoutePlan(BaseModel):
    """保存一轮请求中按顺序执行的一个或多个工具步骤。"""

    steps: list[RouteResult] = Field(min_length=1, max_length=7)
    confidence: float = Field(default=0.5, ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    continue_on_error: bool = True

    @property
    def primary(self) -> RouteResult:
        """返回计划中的第一个工具步骤，便于兼容单工具调用。"""
        return self.steps[0]
