"""提供 确定性业务校验；本文件负责 `itinerary_validator` 相关实现。"""

from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, Field

from schemas.itinerary import Activity, Itinerary


class ItineraryValidationResult(BaseModel):
    """承载 行程、校验 的结构化结果。"""
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ItineraryValidator:
    """集中实现 `ItineraryValidator` 对应的确定性业务逻辑。"""

    def validate(self, itinerary: Itinerary) -> ItineraryValidationResult:
        """汇总检查行程的时间、预算、强度和路线可行性。"""
        errors: list[str] = []
        warnings: list[str] = []

        if itinerary.travel_days and len(itinerary.days) != itinerary.travel_days:
            warnings.append("行程天数与每日行程数量不一致。")

        seen_days: set[int] = set()
        for day in itinerary.days:
            if day.day in seen_days:
                errors.append(f"第 {day.day} 天重复。")
            seen_days.add(day.day)

            if not day.activities:
                warnings.append(f"第 {day.day} 天没有活动。")
                continue

            self._validate_time_sequence(day.day, day.activities, errors, warnings)
            self._validate_route_references(day.day, day.activities, day.routes, errors, warnings)
            self._validate_intensity(day.day, day.activities, warnings)

            if day.estimated_daily_cost is not None and day.estimated_daily_cost < 0:
                errors.append(f"第 {day.day} 天费用不能为负数。")

        self._validate_budget(itinerary, warnings)
        self._validate_route_feasibility(itinerary, warnings)

        return ItineraryValidationResult(is_valid=not errors, errors=errors, warnings=warnings)

    @staticmethod
    def _validate_time_sequence(day: int, activities: list[Activity], errors: list[str], warnings: list[str]) -> None:
        """检查每日活动起止时间是否合法且不存在重叠。"""
        previous_end: time | None = None
        previous_name: str | None = None
        for activity in activities:
            start = _parse_time(activity.start_time)
            end = _parse_time(activity.end_time)
            if start and end and end <= start:
                errors.append(f"第 {day} 天活动 {activity.name} 的结束时间早于或等于开始时间。")
            if previous_end and start and start < previous_end:
                errors.append(f"第 {day} 天活动 {activity.name} 与前一活动 {previous_name} 时间重叠。")
            if end:
                previous_end = end
                previous_name = activity.name

    @staticmethod
    def _validate_route_references(
        day: int,
        activities: list[Activity],
        routes: list[Any],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        """检查活动间路线引用是否完整且指向有效活动。"""
        activity_ids = {activity.activity_id for activity in activities}
        for route in routes:
            if route.origin_activity_id not in activity_ids or route.destination_activity_id not in activity_ids:
                errors.append(f"第 {day} 天路线 {route.route_id} 引用了不存在的活动。")
            if route.verification_status == "unknown":
                warnings.append(f"第 {day} 天路线 {route.route_id} 尚未核验。")
            if route.duration_minutes is not None and route.duration_minutes > 240:
                warnings.append(f"第 {day} 天路线 {route.route_id} 交通时间超过 4 小时。")

    @staticmethod
    def _validate_intensity(day: int, activities: list[Activity], warnings: list[str]) -> None:
        """校验intensity并返回校验结果。"""
        count = len(activities)
        if count > 5:
            warnings.append(f"第 {day} 天主要活动数量为 {count} 个，节奏可能过紧。")
        estimated_minutes = 0
        for activity in activities:
            start = _parse_time(activity.start_time)
            end = _parse_time(activity.end_time)
            if start and end and end > start:
                estimated_minutes += (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        if estimated_minutes > 600:
            warnings.append(f"第 {day} 天活动总时长约 {estimated_minutes} 分钟，可能过累。")

    @staticmethod
    def _validate_budget(itinerary: Itinerary, warnings: list[str]) -> None:
        """校验预算并返回校验结果。"""
        activity_total = sum(
            activity.estimated_cost or 0 for day in itinerary.days for activity in day.activities
        )
        daily_total = sum(day.estimated_daily_cost or 0 for day in itinerary.days)
        calculated_total = max(activity_total, daily_total)
        if calculated_total and itinerary.total_estimated_cost is not None:
            if calculated_total > itinerary.total_estimated_cost * 1.1:
                warnings.append("行程费用合计可能超过总预算 10% 以上。")
            if abs(itinerary.total_estimated_cost - calculated_total) > itinerary.total_estimated_cost * 0.2:
                warnings.append("行程总费用与活动/每日费用合计差异较大，建议复核。")

    @staticmethod
    def _validate_route_feasibility(itinerary: Itinerary, warnings: list[str]) -> None:
        """根据交通耗时和活动间隔检查路线是否可执行。"""
        for day in itinerary.days:
            for activity in day.activities:
                if activity.verification_status == "unknown" and activity.poi is None:
                    warnings.append(f"活动 {activity.name} 尚未通过外部 POI 核验。")


def _parse_time(value: str | None) -> time | None:
    """解析time，供后续流程使用。"""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None
