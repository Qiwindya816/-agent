"""提供 工作流可调用工具；本文件负责 `schemas` 相关实现。"""

from __future__ import annotations

from typing import Any


def object_schema(properties: dict[str, dict[str, Any]], required: list[str] | None = None) -> dict[str, Any]:
    """处理 `object_schema` 对应的数据和流程，返回该步骤的处理结果。"""
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOL_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "check_weather": object_schema(
        {
            "location": {"type": "string"},
            "days": {"type": "integer", "minimum": 1, "maximum": 16},
        },
        ["location"],
    ),
    "convert_currency": object_schema(
        {
            "amount": {"type": "number"},
            "from_currency": {"type": "string"},
            "to_currency": {"type": "string"},
        },
        ["amount", "from_currency", "to_currency"],
    ),
    "search_poi": object_schema(
        {
            "keywords": {"type": "string"},
            "city": {"type": "string"},
            "citylimit": {"type": "boolean"},
        },
        ["keywords"],
    ),
    "search_poi_detail": object_schema({"id": {"type": "string"}}, ["id"]),
    "geocode": object_schema(
        {
            "address": {"type": "string"},
            "city": {"type": "string"},
        },
        ["address"],
    ),
    "plan_route": object_schema(
        {
            "origin": {"type": "string", "description": "经度,纬度"},
            "destination": {"type": "string", "description": "经度,纬度"},
            "city": {"type": "string"},
            "cityd": {"type": "string"},
        },
        ["origin", "destination", "city", "cityd"],
    ),
    "search_train_stations": object_schema({"query": {"type": "string"}}, ["query"]),
    "query_train_tickets": object_schema(
        {
            "from_station": {"type": "string"},
            "to_station": {"type": "string"},
            "train_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        },
        ["from_station", "to_station", "train_date"],
    ),
    "query_train_price": object_schema(
        {
            "from_station": {"type": "string"},
            "to_station": {"type": "string"},
            "train_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "train_code": {"type": "string"},
        },
        ["from_station", "to_station", "train_date"],
    ),
    "query_train_transfer": object_schema(
        {
            "from_station": {"type": "string"},
            "to_station": {"type": "string"},
            "train_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        },
        ["from_station", "to_station", "train_date"],
    ),
    "query_train_route": object_schema(
        {
            "train_no": {"type": "string"},
            "from_station": {"type": "string"},
            "to_station": {"type": "string"},
            "train_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        },
        ["train_no", "from_station", "to_station", "train_date"],
    ),
}


TOOL_OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "check_weather": {"type": "object", "x-model": "NormalizedWeather"},
    "convert_currency": {"type": "object", "x-model": "ExchangeResult"},
    "search_poi": {"type": "array", "items": {"type": "object", "x-model": "NormalizedPoi"}},
    "geocode": {"type": "array", "items": {"type": "object", "x-model": "NormalizedGeocode"}},
    "plan_route": {"type": "object", "x-model": "NormalizedRoute"},
    "search_train_stations": {"type": "array", "items": {"type": "object", "x-model": "NormalizedTrainStation"}},
    "query_train_tickets": {"type": "array", "items": {"type": "object", "x-model": "NormalizedTrainTicket"}},
    "query_train_price": {"type": "array", "items": {"type": "object", "x-model": "NormalizedTrainTicket"}},
    "query_train_transfer": {"type": "array", "items": {"type": "object", "x-model": "NormalizedTrainTicket"}},
    "query_train_route": {"type": "object", "x-model": "NormalizedRoute"},
}


def tool_output_schema(name: str) -> dict[str, Any]:
    """返回指定工具对应的结构化输出 JSON Schema。"""
    return TOOL_OUTPUT_SCHEMAS.get(name, {})
