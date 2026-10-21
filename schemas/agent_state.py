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
    """定义 聊天、消息 的结构化数据模型。"""
    role: Literal["user", "assistant", "system"]  # 消息角色：user/assistant/system
    content: str  # 消息文本内容

# 定义 AgentState 模型，用于保存当前会话的状态信息，包括用户 ID、会话 ID、请求 ID、当前阶段、上一次意图、上一次使用的工具名称、当前行程、预算计划、天气信息、汇率信息、上一次错误信息、用户资料和聊天历史记录。
class AgentState(BaseModel):
    """保存 Agent 的结构化状态。"""
    schema_version: str = "2.0"  # 状态结构版本
    user_id: str = "default_user"  # 用户唯一标识
    session_id: str = "default_session"  # 会话唯一标识
    request_id: str | None = None  # 本轮请求 ID
    trip_id: str = Field(default_factory=new_trip_id)  # 当前行程 ID
    current_stage: AgentStage = "collecting_preferences"  # 当前处理阶段
    last_intent: str | None = None  # 最近识别意图
    last_tool_name: str | None = None  # 最近执行工具
    last_tool_names: list[str] = Field(default_factory=list)  # 本轮工具列表
    route_confidence: float | None = None  # 路由置信度
    current_itinerary: str | None = None  # 当前行程 Markdown 视图
    structured_itinerary: Itinerary | None = None  # 当前结构化行程
    budget_plan: str | None = None  # 预算方案文本
    weather_info: dict | None = None  # 天气结果
    exchange_info: dict | None = None  # 汇率结果
    last_error: str | None = None  # 最近错误码
    user_profile: UserProfile = Field(default_factory=UserProfile)  # 长期用户画像
    travel_request: TravelRequest = Field(default_factory=TravelRequest)  # 本次旅行约束
    chat_history: list[ChatMessage] = Field(default_factory=list)  # 聊天历史
    conversation_summary: str | None = None  # 长对话的结构化摘要
    output_version: int = 0  # 输出版本号
    last_memory_result: dict | None = None  # 最近一轮记忆写入结果
    active_memories: list[dict] = Field(default_factory=list)  # 当前注入的长期记忆
