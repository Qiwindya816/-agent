from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.user_profile import UserProfile
from schemas.travel_request import TravelRequest
from schemas.itinerary import Itinerary
from utils.ids import new_trip_id


AgentStage = Literal[
    "collecting_preferences",
    "recommending_destination",
    "planning_itinerary",
    "refining_itinerary",
    "estimating_budget",
    "checking_weather",
    "searching_places",
    "geocoding",
    "planning_route",
    "converting_currency",
    "finalizing_plan",
]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

# 定义 AgentState 模型，用于保存当前会话的状态信息，包括用户 ID、会话 ID、请求 ID、当前阶段、上一次意图、上一次使用的工具名称、当前行程、预算计划、天气信息、汇率信息、上一次错误信息、用户资料和聊天历史记录。
class AgentState(BaseModel):
    schema_version: str = "2.0"
    user_id: str = "default_user"
    session_id: str = "default_session"
    request_id: str | None = None
    trip_id: str = Field(default_factory=new_trip_id)
    current_stage: AgentStage = "collecting_preferences"
    last_intent: str | None = None
    last_tool_name: str | None = None
    last_tool_names: list[str] = Field(default_factory=list)
    route_confidence: float | None = None
    current_itinerary: str | None = None
    structured_itinerary: Itinerary | None = None
    budget_plan: str | None = None
    weather_info: dict | None = None
    exchange_info: dict | None = None
    last_error: str | None = None
    user_profile: UserProfile = Field(default_factory=UserProfile)
    travel_request: TravelRequest = Field(default_factory=TravelRequest)
    chat_history: list[ChatMessage] = Field(default_factory=list)
    output_version: int = 0
