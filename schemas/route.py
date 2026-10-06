from typing import Any

from pydantic import BaseModel, Field


TOOL_STAGE_MAP = {
    "recommend_destination": "recommending_destination",
    "plan_itinerary": "planning_itinerary",
    "refine_itinerary": "refining_itinerary",
    "edit_itinerary_activity": "editing_itinerary_activity",
    "estimate_budget": "estimating_budget",
    "check_weather": "checking_weather",
    "search_poi": "searching_places",
    "geocode": "geocoding",
    "plan_route": "planning_route",
    "search_train_stations": "searching_train_stations",
    "query_train_tickets": "querying_train_tickets",
    "query_train_price": "querying_train_price",
    "query_train_transfer": "querying_train_transfer",
    "query_train_route": "querying_train_route",
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
    arguments: dict[str, Any] = Field(default_factory=dict)

    @property
    def origin_activity_id(self) -> str | None:
        """获取起点 `origin_activity_id` 对应的数据和流程，返回该步骤的处理结果。"""
        value = self.arguments.get("origin_activity_id")
        return str(value) if value else None

    @property
    def destination_activity_id(self) -> str | None:
        """获取终点 `destination_activity_id` 对应的数据和流程，返回该步骤的处理结果。"""
        value = self.arguments.get("destination_activity_id")
        return str(value) if value else None

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
