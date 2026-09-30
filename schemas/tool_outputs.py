"""Normalized output models for external tool providers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ExternalFact(BaseModel):
    """Common provider and freshness metadata for an external fact."""

    provider: str
    source_id: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None


class NormalizedPoi(BaseModel):
    """A provider-independent POI record."""

    poi_id: str
    rating: float | None = None
    opening_hours: str | None = None
    name: str
    address: str | None = None
    city: str | None = None
    district: str | None = None
    category: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    source: ExternalFact


class NormalizedGeocode(BaseModel):
    """A provider-independent geocoding result."""

    address: str
    formatted_address: str | None = None
    city: str | None = None
    district: str | None = None
    adcode: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    source: ExternalFact


class NormalizedRouteStep(BaseModel):
    """A coarse route instruction without provider-specific fields."""

    instruction: str | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None


class NormalizedRoute(BaseModel):
    """A provider-independent route result."""

    origin: str
    destination: str
    mode: str = "transit"
    distance_meters: int | None = None
    duration_seconds: int | None = None
    walking_distance_meters: int | None = None
    steps: list[NormalizedRouteStep] = Field(default_factory=list)
    source: ExternalFact


class NormalizedTrainStation(BaseModel):
    """A railway station record."""

    station_name: str
    station_code: str | None = None
    pinyin: str | None = None
    source: ExternalFact


class NormalizedTrainSeat(BaseModel):
    """A seat class and its textual availability/price."""

    seat_class: str
    value: str


class NormalizedTrainTicket(BaseModel):
    """A train option returned by the railway provider."""

    train_no: str
    departure_station: str
    departure_station_code: str | None = None
    arrival_station: str | None = None
    arrival_station_code: str | None = None
    departure_time: str | None = None
    arrival_time: str | None = None
    duration: str | None = None
    seats: list[NormalizedTrainSeat] = Field(default_factory=list)
    source: ExternalFact


class NormalizedWeatherDay(BaseModel):
    """A daily forecast record."""

    date: str
    weather: str
    min_temperature: float | None = None
    max_temperature: float | None = None
    precipitation: float | None = None


class NormalizedWeather(BaseModel):
    """A provider-independent forecast."""

    location: str
    latitude: float | None = None
    longitude: float | None = None
    days: list[NormalizedWeatherDay] = Field(default_factory=list)
    source: ExternalFact


def parse_poi_response(data: Any, provider: str = "amap") -> list[NormalizedPoi]:
    """Normalize an Amap POI response into NormalizedPoi records."""
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
    """Normalize an Amap geocode response."""
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
    """Normalize an Amap transit route response at a high level."""
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
    """Normalize a railway station search response."""
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
    """Normalize a railway ticket query response."""
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
    """Extract a normalized weather object from the current Markdown table."""
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
    import json

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value


def _split_location(value: Any) -> tuple[float | None, float | None]:
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
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _first_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
