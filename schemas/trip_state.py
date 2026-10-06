from datetime import datetime

from pydantic import BaseModel, Field

from schemas.travel_request import TravelRequest
from schemas.itinerary import Itinerary


class ItineraryVersion(BaseModel):
    """定义 行程、版本 的结构化数据模型。"""
    version: int
    itinerary_markdown: str
    structured_itinerary: Itinerary | None = None
    user_feedback: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

# 定义旅行状态的统一数据结构，包含行程 ID、标题、旅行请求、当前行程、预算计划、行程版本列表、状态和时间戳等信息。
class TripState(BaseModel):
    """保存 旅行 的结构化状态。"""
    schema_version: str = "2.0"
    trip_id: str
    user_id: str | None = None
    session_id: str | None = None
    title: str | None = None
    travel_request: TravelRequest = Field(default_factory=TravelRequest)
    current_itinerary: str | None = None
    structured_itinerary: Itinerary | None = None
    budget_plan: str | None = None
    weather_info: dict | None = None
    exchange_info: dict | None = None
    itinerary_versions: list[ItineraryVersion] = Field(default_factory=list)
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
