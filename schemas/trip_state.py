from datetime import datetime

from pydantic import BaseModel, Field

from schemas.travel_request import TravelRequest
from schemas.itinerary import Itinerary


class ItineraryVersion(BaseModel):
    """定义 行程、版本 的结构化数据模型。"""
    version: int  # 版本号
    itinerary_markdown: str  # Markdown 行程
    structured_itinerary: Itinerary | None = None  # 结构化行程
    user_feedback: str | None = None  # 用户反馈
    changed_fields: list[str] = Field(default_factory=list)  # 变更字段
    created_at: datetime = Field(default_factory=datetime.utcnow)  # 创建时间

# 定义旅行状态的统一数据结构，包含行程 ID、标题、旅行请求、当前行程、预算计划、行程版本列表、状态和时间戳等信息。
class TripState(BaseModel):
    """保存 旅行 的结构化状态。"""
    schema_version: str = "2.0"  # 版本
    trip_id: str  # 行程 ID
    user_id: str | None = None  # 用户 ID
    session_id: str | None = None  # 会话 ID
    title: str | None = None  # 标题
    travel_request: TravelRequest = Field(default_factory=TravelRequest)  # 旅行约束
    current_itinerary: str | None = None  # Markdown 行程
    structured_itinerary: Itinerary | None = None  # 结构化行程
    budget_plan: str | None = None  # 预算
    weather_info: dict | None = None  # 天气
    exchange_info: dict | None = None  # 汇率
    itinerary_versions: list[ItineraryVersion] = Field(default_factory=list)  # 版本列表
    status: str = "active"  # 状态
    created_at: datetime = Field(default_factory=datetime.utcnow)  # 创建时间
    updated_at: datetime = Field(default_factory=datetime.utcnow)  # 更新时间
