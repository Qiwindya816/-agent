"""提供 核心领域服务和外部服务适配；本文件负责 `itinerary_enricher` 相关实现。"""

from __future__ import annotations

from typing import Any

from schemas.itinerary import Activity, GeoPoint, Itinerary, POIReference, RouteSegment, TransportOption
from schemas.tool import ToolResult
from schemas.tool_outputs import (
    NormalizedPoi,
    NormalizedRoute,
    parse_poi_response,
    parse_route_response,
    parse_weather_markdown,
)


class ItineraryEnricher:
    """封装 `ItineraryEnricher` 的核心数据与行为。"""

    def enrich_from_poi(self, itinerary: Itinerary, result: ToolResult, detail_tool: Any | None = None) -> Itinerary:
        """丰富 `enrich_from_poi` 对应的数据和流程，返回该步骤的处理结果。"""
        pois = parse_poi_response(result.data, provider=str(result.metadata.get("provider", "amap")))
        if detail_tool is not None and pois and pois[0].longitude is None:
            detail = detail_tool.run({"mcp_arguments": {"id": pois[0].poi_id}})
            if detail.success:
                detailed = parse_poi_response(detail.data, provider=str(detail.metadata.get("provider", "amap")))
                if detailed and detailed[0].longitude is not None:
                    pois[0] = detailed[0]
        if not pois:
            return itinerary
        by_name = {poi.name.lower(): poi for poi in pois}
        for activity in self._activities(itinerary):
            candidate = by_name.get(activity.name.lower())
            if candidate is None:
                continue
            activity.poi = self._poi_reference(candidate)
            activity.verification_status = "verified"
            if not activity.location:
                activity.location = candidate.address
        return itinerary

    def enrich_from_route(self, itinerary: Itinerary, result: ToolResult, day_number: int = 1, route: Any | None = None) -> Itinerary:
        """丰富 `enrich_from_route` 对应的数据和流程，返回该步骤的处理结果。"""
        route = parse_route_response(result.data, provider=str(result.metadata.get("provider", "amap")))
        if route is None or not itinerary.days:
            return itinerary
        day = next((item for item in itinerary.days if item.day == day_number), itinerary.days[0])
        if len(day.activities) < 2:
            return itinerary

        origin_id = getattr(route, "origin_activity_id", None) if route is not None else None
        destination_id = getattr(route, "destination_activity_id", None) if route is not None else None
        origin_activity = next((item for item in day.activities if item.activity_id == origin_id), None)
        destination_activity = next((item for item in day.activities if item.activity_id == destination_id), None)
        if origin_activity is None or destination_activity is None:
            # 路线响应只有坐标而没有活动名称。在 Planner 提供明确活动 ID 前，
            # 暂时将路线绑定到排序后的前两个活动。
            origin_activity = day.activities[0]
            destination_activity = day.activities[1]

        segment = RouteSegment(
            origin_activity_id=origin_activity.activity_id,
            destination_activity_id=destination_activity.activity_id,
            mode="transit",
            distance_meters=route.distance_meters,
            duration_minutes=(route.duration_seconds // 60) if route.duration_seconds is not None else None,
            verification_status="verified",
        )
        day.routes = [segment]
        return itinerary

    def add_transport_options(self, itinerary: Itinerary, result: ToolResult, train_date: str | None = None) -> Itinerary:
        """添加 `add_transport_options` 对应的数据和流程，返回该步骤的处理结果。"""
        from schemas.tool_outputs import parse_train_ticket_response

        tickets = parse_train_ticket_response(result.data, provider=str(result.metadata.get("provider", "railway-12306")))
        itinerary.transport_options = [
            TransportOption(
                transport_type="train",
                date=train_date,
                from_station=ticket.departure_station,
                to_station=ticket.arrival_station,
                train_no=ticket.train_no,
                departure_time=ticket.departure_time,
                arrival_time=ticket.arrival_time,
                duration=ticket.duration,
                seats={seat.seat_class: seat.value for seat in ticket.seats},
                verification_status="verified",
            )
            for ticket in tickets
        ]
        return itinerary

    def add_weather_warning(self, itinerary: Itinerary, result: ToolResult, day_number: int = 1) -> Itinerary:
        """添加 `add_weather_warning` 对应的数据和流程，返回该步骤的处理结果。"""
        weather = parse_weather_markdown(str(result.data))
        if weather is None or not itinerary.days:
            return itinerary
        day = next((item for item in itinerary.days if item.day == day_number), itinerary.days[0])
        rain_days = [item for item in weather.days if (item.precipitation or 0) > 0]
        if rain_days:
            itinerary.warnings = list(dict.fromkeys([*itinerary.warnings, f"第 {day.day} 天可能降水，建议准备室内替代方案。"]))
        return itinerary

    @staticmethod
    def _activities(itinerary: Itinerary) -> list[Activity]:
        """遍历行程中的全部活动。"""
        return [activity for day in itinerary.days for activity in day.activities]

    @staticmethod
    def _poi_reference(poi: NormalizedPoi) -> POIReference:
        """从工具结果中提取可关联到活动的 POI 引用。"""
        return POIReference(
            provider=poi.source.provider,
            poi_id=poi.poi_id,
            name=poi.name,
            address=poi.address,
            location=(
                GeoPoint(
                    longitude=poi.longitude,
                    latitude=poi.latitude,
                    coordinate_system="GCJ-02",
                )
                if poi.longitude is not None and poi.latitude is not None
                else None
            ),
        )
