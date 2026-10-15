from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def _new_id(prefix: str) -> str:
    """生成带指定前缀的短唯一标识。"""
    return f"{prefix}_{uuid4().hex}"


class ExternalSource(BaseModel):
    """外部事实的来源和时效信息。"""

    provider: str  # 数据提供方
    source_id: str | None = None  # 来源 ID
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))  # 获取时间
    expires_at: datetime | None = None  # 过期时间
    url: str | None = None  # 来源链接


class GeoPoint(BaseModel):
    """带坐标系标识的地理坐标。"""

    longitude: float = Field(ge=-180, le=180)  # 经度
    latitude: float = Field(ge=-90, le=90)  # 纬度
    coordinate_system: Literal["GCJ-02", "WGS84", "BD-09"] = "GCJ-02"  # 坐标系


class POIReference(BaseModel):
    """行程活动引用的真实地点；未知信息保持为空。"""

    provider: str  # POI 提供方
    poi_id: str  # POI ID
    name: str  # 名称
    address: str | None = None  # 地址
    location: GeoPoint | None = None  # 坐标
    source: ExternalSource | None = None  # 来源和时效信息


class RouteSegment(BaseModel):
    """两个活动之间可被外部地图服务核验的路线段。"""

    route_id: str = Field(default_factory=lambda: _new_id("route"))  # 路线段 ID
    origin_activity_id: str  # 起点活动 ID
    destination_activity_id: str  # 终点活动 ID
    mode: Literal["walking", "driving", "transit", "cycling", "unknown"] = "unknown"  # 交通方式
    distance_meters: int | None = Field(default=None, ge=0)  # 距离（米）
    duration_minutes: int | None = Field(default=None, ge=0)  # 耗时（分钟）
    verification_status: Literal["verified", "estimated", "unknown"] = "unknown"  # 核验状态
    source: ExternalSource | None = None  # 来源


class Activity(BaseModel):
    """定义 活动 的结构化数据模型。"""
    activity_id: str = Field(default_factory=lambda: _new_id("activity"))  # 活动 ID
    name: str  # 活动名称
    category: str | None = None  # 类别
    start_time: str | None = None  # 开始时间
    end_time: str | None = None  # 结束时间
    location: str | None = None  # 地点文本
    estimated_cost: float | None = Field(default=None, ge=0)  # 预估费用
    transport_method: str | None = None  # 交通方式
    notes: str | None = None  # 备注
    poi: POIReference | None = None  # 真实 POI 引用
    verification_status: Literal["verified", "estimated", "unknown"] = "unknown"  # 核验状态


class TransportOption(BaseModel):
    """封装 `TransportOption` 的核心数据与行为。"""

    option_id: str = Field(default_factory=lambda: _new_id("transport"))  # 交通选项 ID
    transport_type: Literal["train", "flight", "bus", "car", "unknown"] = "unknown"  # 交通类型
    date: str | None = None  # 日期
    from_station: str | None = None  # 出发站
    to_station: str | None = None  # 到达站
    train_no: str | None = None  # 车次
    departure_time: str | None = None  # 出发时间
    arrival_time: str | None = None  # 到达时间
    duration: str | None = None  # 历时
    seats: dict[str, str] = Field(default_factory=dict)  # 席别和余票/价格
    verification_status: Literal["verified", "estimated", "unknown"] = "unknown"  # 核验状态


class DailyItinerary(BaseModel):
    """定义 每日、行程 的结构化数据模型。"""
    day: int = Field(ge=1)  # 第几天
    date: str | None = None  # 日期
    theme: str | None = None  # 当日主题
    activities: list[Activity] = Field(default_factory=list)  # 活动列表
    routes: list[RouteSegment] = Field(default_factory=list)  # 活动间路线段
    estimated_daily_cost: float | None = Field(default=None, ge=0)  # 当日预估费用


class Itinerary(BaseModel):
    """定义 行程 的结构化数据模型。"""
    schema_version: str = "3.0"  # 结构版本
    title: str | None = None  # 行程标题
    departure_city: str | None = None  # 出发城市
    destination: str | None = None  # 目的地
    travel_days: int | None = Field(default=None, ge=1)  # 旅行天数
    currency: str = Field(default="CNY", min_length=3, max_length=3)  # 币种
    days: list[DailyItinerary] = Field(default_factory=list)  # 按天行程
    transport_options: list[TransportOption] = Field(default_factory=list)  # 城际交通选项
    total_estimated_cost: float | None = Field(default=None, ge=0)  # 总预算
    assumptions: list[str] = Field(default_factory=list)  # 假设
    warnings: list[str] = Field(default_factory=list)  # 警告
    accommodation_area: str | None = None  # 建议住宿区域
    general_transport_advice: str | None = None  # 总体交通建议

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
