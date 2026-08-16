from pydantic import BaseModel, Field

from schemas.itinerary import Itinerary


class ItineraryValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ItineraryValidator:
    def validate(self, itinerary: Itinerary) -> ItineraryValidationResult:
        """检查行程天数、重复日期、空活动及负费用等问题。"""
        errors = []
        warnings = []

        if itinerary.travel_days and len(itinerary.days) != itinerary.travel_days:
            warnings.append("行程天数与每日行程数量不一致。")

        seen_days = set()
        for day in itinerary.days:
            if day.day in seen_days:
                errors.append(f"第 {day.day} 天重复。")
            seen_days.add(day.day)
            if not day.activities:
                warnings.append(f"第 {day.day} 天没有活动。")
            if day.estimated_daily_cost is not None and day.estimated_daily_cost < 0:
                errors.append(f"第 {day.day} 天费用不能为负数。")

        return ItineraryValidationResult(is_valid=not errors, errors=errors, warnings=warnings)
