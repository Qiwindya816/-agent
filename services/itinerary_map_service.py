"""提供 核心领域服务和外部服务适配；本文件负责 `itinerary_map_service` 相关实现。"""

from __future__ import annotations

import re
from typing import Any

from schemas.itinerary import GeoPoint, Itinerary, POIReference
from schemas.tool import ToolResult


_NON_PLACE_WORDS = (
    "早餐", "午餐", "晚餐", "用餐", "休息", "退房", "寄存", "前往", "返回", "抵达",
)


class ItineraryMapService:
    """提供 `ItineraryMapService` 对应领域能力的统一服务。"""

    def enrich(self, itinerary: Itinerary, geocode_tool: Any, state: Any) -> tuple[Itinerary, ToolResult, int]:
        """为行程中的地点补充地图坐标，供前端绘制轨迹。"""
        query_activities: dict[str, list[Any]] = {}
        destination = (itinerary.destination or "").strip()
        for day in itinerary.days:
            for activity in day.activities:
                if activity.poi and activity.poi.location:
                    continue
                query = self._query_for(activity.name, destination)
                if query:
                    query_activities.setdefault(query, []).append(activity)

        if not query_activities:
            result = ToolResult.ok("geocode", {"results": []}, {"provider": "amap"})
            return itinerary, result, 0

        result = geocode_tool.run(
            {
                "state": state,
                "mcp_arguments": {"addresses": list(query_activities), "city": destination},
            }
        )
        if not result.success:
            return itinerary, result, 0

        payload = result.data if isinstance(result.data, dict) else {}
        resolved = 0
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            query = str(item.get("address") or "")
            coordinates = self._coordinates(item.get("location"))
            if not coordinates:
                continue
            for activity in query_activities.get(query, []):
                longitude, latitude = coordinates
                activity.poi = POIReference(
                    provider="amap",
                    poi_id=f"geocode:{activity.activity_id}",
                    name=activity.name,
                    address=activity.location or query,
                    location=GeoPoint(
                        longitude=longitude,
                        latitude=latitude,
                        coordinate_system="GCJ-02",
                    ),
                )
                activity.verification_status = "verified"
                resolved += 1
        return itinerary, result, resolved

    @staticmethod
    def _query_for(name: str, destination: str) -> str | None:
        """为行程活动构造地理编码查询文本。"""
        cleaned = re.sub(r"[（(].*?[）)]", "", name).strip(" -—·")
        if not cleaned or any(word in cleaned for word in _NON_PLACE_WORDS):
            return None
        return f"{destination}{cleaned}" if destination and destination not in cleaned else cleaned

    @staticmethod
    def _coordinates(value: Any) -> tuple[float, float] | None:
        """从地理编码结果中提取经纬度坐标。"""
        if not isinstance(value, str):
            return None
        parts = value.split(",")
        if len(parts) != 2:
            return None
        try:
            longitude, latitude = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            return None
        return longitude, latitude
