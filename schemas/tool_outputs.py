"""提供 Pydantic 结构化数据模型；本文件负责 `tool_outputs` 相关实现。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ExternalFact(BaseModel):
    """封装 `ExternalFact` 的核心数据与行为。"""

    provider: str  # 提供方
    source_id: str | None = None  # 来源 ID
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))  # 获取时间
    expires_at: datetime | None = None  # 过期时间


class NormalizedPoi(BaseModel):
    """封装 `NormalizedPoi` 的核心数据与行为。"""

    poi_id: str  # POI ID
    rating: float | None = None  # 评分
    opening_hours: str | None = None  # 开放时间
    name: str  # 名称
    address: str | None = None  # 地址
    city: str | None = None  # 城市
    district: str | None = None  # 区域
    category: str | None = None  # 类别
    longitude: float | None = None  # 经度
    latitude: float | None = None  # 纬度
    source: ExternalFact  # 来源


class NormalizedGeocode(BaseModel):
    """封装 `NormalizedGeocode` 的核心数据与行为。"""

    address: str  # 地址
    formatted_address: str | None = None  # 格式化地址
    city: str | None = None  # 城市
    district: str | None = None  # 区域
    adcode: str | None = None  # 行政区划代码
    longitude: float | None = None  # 经度
    latitude: float | None = None  # 纬度
    source: ExternalFact  # 来源


class NormalizedRouteStep(BaseModel):
    """封装 `NormalizedRouteStep` 的核心数据与行为。"""

    instruction: str | None = None  # 指引
    distance_meters: int | None = None  # 距离
    duration_seconds: int | None = None  # 耗时


class NormalizedRoute(BaseModel):
    """封装 `NormalizedRoute` 的核心数据与行为。"""

    origin: str  # 起点
    destination: str  # 终点
    mode: str = "transit"  # 交通方式
    distance_meters: int | None = None  # 距离
    duration_seconds: int | None = None  # 耗时
    walking_distance_meters: int | None = None  # 步行距离
    steps: list[NormalizedRouteStep] = Field(default_factory=list)  # 步骤
    source: ExternalFact  # 来源


class NormalizedTrainStation(BaseModel):
    """封装 `NormalizedTrainStation` 的核心数据与行为。"""

    station_name: str  # 站名
    station_code: str | None = None  # 车站代码
    pinyin: str | None = None  # 拼音
    source: ExternalFact  # 来源


class NormalizedTrainSeat(BaseModel):
    """封装 `NormalizedTrainSeat` 的核心数据与行为。"""

    seat_class: str  # 席别
    value: str  # 余票/价格文本


class NormalizedTrainTicket(BaseModel):
    """封装 `NormalizedTrainTicket` 的核心数据与行为。"""

    train_no: str  # 车次
    departure_station: str  # 出发站
    departure_station_code: str | None = None  # 出发站代码
    arrival_station: str | None = None  # 到达站
    arrival_station_code: str | None = None  # 到达站代码
    departure_time: str | None = None  # 出发时间
    arrival_time: str | None = None  # 到达时间
    duration: str | None = None  # 历时
    seats: list[NormalizedTrainSeat] = Field(default_factory=list)  # 席别列表
    source: ExternalFact  # 来源


class NormalizedWeatherDay(BaseModel):
    """封装 `NormalizedWeatherDay` 的核心数据与行为。"""

    date: str  # 日期
    weather: str  # 天气
    min_temperature: float | None = None  # 最低温
    max_temperature: float | None = None  # 最高温
    precipitation: float | None = None  # 降水量


class NormalizedWeather(BaseModel):
    """封装 `NormalizedWeather` 的核心数据与行为。"""

    location: str  # 地点
    latitude: float | None = None  # 纬度
    longitude: float | None = None  # 经度
    days: list[NormalizedWeatherDay] = Field(default_factory=list)  # 每日天气
    source: ExternalFact  # 来源


def parse_poi_response(data: Any, provider: str = "amap") -> list[NormalizedPoi]:
    """解析 `parse_poi_response` 对应的数据和流程，返回该步骤的处理结果。"""
    payload = _decode_json(data)
    pois = payload.get("pois", []) if isinstance(payload, dict) else []
    if not pois and isinstance(payload, dict) and payload.get("id"):
        pois = [payload]
    result: list[NormalizedPoi] = []
    for item in pois:
        if not isinstance(item, dict):
            continue
        location = _split_location(item.get("location") or item.get("lonlat") or item.get("coordinate"))
        result.append(
            NormalizedPoi(
                poi_id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                address=item.get("address"),
                rating=_first_float(item.get("rating")) if item.get("rating") is not None else None,
                city=item.get("cityname") or item.get("city"),
                district=item.get("adname") or item.get("district"),
                category=item.get("type") or item.get("typecode"),
                longitude=location[0],
                latitude=location[1],
                opening_hours=item.get("opentime2") or item.get("open_time"),
                source=ExternalFact(provider=provider, source_id=item.get("id")),
            )
        )
    return result


def parse_geocode_response(data: Any, provider: str = "amap") -> list[NormalizedGeocode]:
    """解析 `parse_geocode_response` 对应的数据和流程，返回该步骤的处理结果。"""
    payload = _decode_json(data)
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    result: list[NormalizedGeocode] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        location = _split_location(item.get("location") or item.get("lonlat") or item.get("coordinate"))
        result.append(
            NormalizedGeocode(
                address=str(item.get("formatted_address") or item.get("address") or ""),
                formatted_address=item.get("formatted_address"),
                city=item.get("city"),
                district=item.get("district"),
                adcode=item.get("adcode"),
                longitude=location[0],
                latitude=location[1],
                source=ExternalFact(provider=provider, source_id=item.get("adcode")),
            )
        )
    return result


def parse_route_response(data: Any, provider: str = "amap") -> NormalizedRoute | None:
    """解析 `parse_route_response` 对应的数据和流程，返回该步骤的处理结果。"""
    payload = _decode_json(data)
    if not isinstance(payload, dict):
        return None
    distance = _to_int(payload.get("distance"))
    transits = payload.get("transits") or []
    duration = None
    walking_distance = None
    steps: list[NormalizedRouteStep] = []
    if transits:
        first = transits[0]
        duration = _to_int(first.get("duration"))
        walking_distance = _to_int(first.get("walking_distance"))
        for segment in first.get("segments", []):
            if not isinstance(segment, dict):
                continue
            bus = segment.get("bus") or {}
            buslines = bus.get("buslines") or []
            if buslines:
                line = buslines[0]
                steps.append(
                    NormalizedRouteStep(
                        instruction=line.get("name"),
                        distance_meters=_to_int(line.get("distance")),
                        duration_seconds=_to_int(line.get("duration")),
                    )
                )
    return NormalizedRoute(
        origin=str(payload.get("origin") or ""),
        destination=str(payload.get("destination") or ""),
        mode="transit",
        distance_meters=distance,
        duration_seconds=duration,
        walking_distance_meters=walking_distance,
        steps=steps,
        source=ExternalFact(provider=provider),
    )


def parse_train_station_response(data: Any, provider: str = "railway-12306") -> list[NormalizedTrainStation]:
    """解析 `parse_train_station_response` 对应的数据和流程，返回该步骤的处理结果。"""
    payload = _decode_json(data)
    rows = payload.get("stations", []) if isinstance(payload, dict) else []
    return [
        NormalizedTrainStation(
            station_name=str(item.get("name") or ""),
            station_code=item.get("code"),
            pinyin=item.get("pinyin"),
            source=ExternalFact(provider=provider, source_id=item.get("code")),
        )
        for item in rows
        if isinstance(item, dict)
    ]


def parse_train_ticket_response(data: Any, provider: str = "railway-12306") -> list[NormalizedTrainTicket]:
    """解析 `parse_train_ticket_response` 对应的数据和流程，返回该步骤的处理结果。"""
    payload = _decode_json(data)
    rows = payload.get("trains", []) if isinstance(payload, dict) else []
    result: list[NormalizedTrainTicket] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        seats = [
            NormalizedTrainSeat(seat_class=seat_class, value=str(value))
            for seat_class, value in (item.get("seats") or {}).items()
            if value not in (None, "")
        ]
        result.append(
            NormalizedTrainTicket(
                train_no=str(item.get("train_no") or item.get("train_code") or ""),
                departure_station=str(item.get("from_station") or ""),
                departure_station_code=item.get("from_station_code"),
                arrival_station=item.get("to_station"),
                arrival_station_code=item.get("to_station_code"),
                departure_time=item.get("start_time"),
                arrival_time=item.get("arrive_time"),
                duration=item.get("duration"),
                seats=seats,
                source=ExternalFact(provider=provider, source_id=item.get("train_no")),
            )
        )
    return result


def parse_weather_markdown(data: str) -> NormalizedWeather | None:
    """解析 `parse_weather_markdown` 对应的数据和流程，返回该步骤的处理结果。"""
    lines = data.splitlines()
    location = None
    days: list[NormalizedWeatherDay] = []
    for line in lines:
        if line.startswith("## "):
            location = line.removeprefix("## ").replace("天气预报", "").strip()
        if line.startswith("|") and "日期" not in line and "---" not in line:
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) >= 4:
                days.append(
                    NormalizedWeatherDay(
                        date=parts[0],
                        weather=parts[1],
                        min_temperature=_first_float(parts[2].split("~")[0]),
                        max_temperature=_first_float(parts[2].split("~")[-1].removesuffix("°C")),
                        precipitation=_first_float(parts[3].removesuffix(" mm")),
                    )
                )
    if location is None:
        return None
    return NormalizedWeather(location=location, days=days, source=ExternalFact(provider="open-meteo"))


def _decode_json(value: Any) -> Any:
    """解码json，供后续流程使用。"""
    import json

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value


def _split_location(value: Any) -> tuple[float | None, float | None]:
    """拆分位置，供后续流程使用。"""
    if not isinstance(value, str):
        return None, None
    parts = value.split(",")
    if len(parts) != 2:
        return None, None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None, None


def _to_int(value: Any) -> int | None:
    """转换为int，供后续流程使用。"""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _first_float(value: str) -> float | None:
    """返回候选值中第一个可转换的浮点数。"""
    try:
        return float(value)
    except ValueError:
        return None
