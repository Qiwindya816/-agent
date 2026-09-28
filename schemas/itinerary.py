from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ExternalSource(BaseModel):
    """外部事实的来源和时效信息。"""

    provider: str
    source_id: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    url: str | None = None


class GeoPoint(BaseModel):
    """带坐标系标识的地理坐标。"""

    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    coordinate_system: Literal["GCJ-02", "WGS84", "BD-09"] = "GCJ-02"


class POIReference(BaseModel):
    """行程活动引用的真实地点；未知信息保持为空。"""

    provider: str
    poi_id: str
    name: str
    address: str | None = None
    location: GeoPoint | None = None
    source: ExternalSource | None = None


class RouteSegment(BaseModel):
    """两个活动之间可被外部地图服务核验的路线段。"""

    route_id: str = Field(default_factory=lambda: _new_id("route"))
    origin_activity_id: str
    destination_activity_id: str
    mode: Literal["walking", "driving", "transit", "cycling", "unknown"] = "unknown"
    distance_meters: int | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=0)
    verification_status: Literal["verified", "estimated", "unknown"] = "unknown"
    source: ExternalSource | None = None


class Activity(BaseModel):
    activity_id: str = Field(default_factory=lambda: _new_id("activity"))
    name: str
    category: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    estimated_cost: float | None = Field(default=None, ge=0)
    transport_method: str | None = None
    notes: str | None = None
    poi: POIReference | None = None
    verification_status: Literal["verified", "estimated", "unknown"] = "unknown"


class DailyItinerary(BaseModel):
    day: int = Field(ge=1)
    date: str | None = None
    theme: str | None = None
    activities: list[Activity] = Field(default_factory=list)
    routes: list[RouteSegment] = Field(default_factory=list)
    estimated_daily_cost: float | None = Field(default=None, ge=0)


class Itinerary(BaseModel):
    schema_version: str = "3.0"
    title: str | None = None
    departure_city: str | None = None
    destination: str | None = None
    travel_days: int | None = Field(default=None, ge=1)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    days: list[DailyItinerary] = Field(default_factory=list)
    total_estimated_cost: float | None = Field(default=None, ge=0)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    accommodation_area: str | None = None
    general_transport_advice: str | None = None

    @model_validator(mode="after")
    def validate_days(self) -> "Itinerary":
        """保证天数和每日编号不会形成自相矛盾的结构。"""
        if self.days and self.travel_days is None:
            self.travel_days = len(self.days)
        if self.days and self.travel_days != len(self.days):
            raise ValueError("travel_days 必须与 days 数量一致。")
        day_numbers = [day.day for day in self.days]
        if len(day_numbers) != len(set(day_numbers)):
            raise ValueError("每天的 day 编号必须唯一。")
        return self
