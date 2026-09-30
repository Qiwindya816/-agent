"""Tests for deterministic weather-based itinerary adjustment."""

from schemas.itinerary import Itinerary
from schemas.tool_outputs import ExternalFact, NormalizedWeather, NormalizedWeatherDay
from services.weather_advisor import WeatherAdvisor


def test_weather_advisor_marks_rainy_outdoor_activities() -> None:
    itinerary = Itinerary.model_validate(
        {
            "travel_days": 1,
            "days": [{"day": 1, "activities": [{"name": "景山公园", "category": "park"}]}],
        }
    )
    weather = NormalizedWeather(
        location="北京",
        source=ExternalFact(provider="open-meteo"),
        days=[NormalizedWeatherDay(date="2026-10-01", weather="小雨", precipitation=12, max_temperature=24)],
    )

    adjusted = WeatherAdvisor().adjust(itinerary, weather)

    assert "室内替代方案" in adjusted.warnings[0]
    assert "雨天建议改为室内活动。" in adjusted.days[0].activities[0].notes


def test_weather_advisor_adds_heat_warning() -> None:
    itinerary = Itinerary.model_validate({"travel_days": 1, "days": [{"day": 1, "activities": []}]})
    weather = NormalizedWeather(
        location="北京",
        source=ExternalFact(provider="open-meteo"),
        days=[NormalizedWeatherDay(date="2026-10-01", weather="晴", precipitation=0, max_temperature=38)],
    )

    adjusted = WeatherAdvisor().adjust(itinerary, weather)

    assert any("最高气温" in warning for warning in adjusted.warnings)
