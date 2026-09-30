"""Adapt itinerary activities to provider-backed weather forecasts."""

from __future__ import annotations

from schemas.itinerary import Itinerary
from schemas.tool_outputs import NormalizedWeather


class WeatherAdvisor:
    """Add deterministic weather advisories and suggest indoor alternatives."""

    def adjust(self, itinerary: Itinerary, weather: NormalizedWeather) -> Itinerary:
        if not weather.days:
            return itinerary
        for index, day in enumerate(itinerary.days):
            forecast = weather.days[index] if index < len(weather.days) else None
            if forecast is None:
                continue
            if (forecast.precipitation or 0) > 0:
                message = f"第 {day.day} 天 {forecast.date} 可能降水（{forecast.precipitation}mm），建议准备室内替代方案。"
                itinerary.warnings = list(dict.fromkeys([*itinerary.warnings, message]))
                for activity in day.activities:
                    if self._is_outdoor(activity.category or activity.name):
                        activity.notes = (activity.notes + "\n" if activity.notes else "") + "雨天建议改为室内活动。"
            if forecast.max_temperature is not None and forecast.max_temperature >= 35:
                message = f"第 {day.day} 天最高气温约 {forecast.max_temperature}°C，建议避免正午户外活动。"
                itinerary.warnings = list(dict.fromkeys([*itinerary.warnings, message]))
        return itinerary

    @staticmethod
    def _is_outdoor(value: str) -> bool:
        return any(word in value.lower() for word in ("park", "mountain", "outdoor", "公园", "山", "长城", "户外"))
