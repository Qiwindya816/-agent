from typing import Any

import requests

from config.settings import get_settings
from schemas.weather import DailyWeather, WeatherResult


OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODE_TEXT = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "较强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    95: "雷暴",
}


class WeatherService:
    def __init__(self) -> None:
        """加载天气接口请求所需的项目配置。"""
        self.settings = get_settings()

    def get_forecast(self, location: str, days: int = 7) -> WeatherResult:
        """查询指定地点未来若干天的天气，并返回统一结果模型。"""
        try:
            place = self._geocode(location)
            response = requests.get(
                OPEN_METEO_FORECAST_URL,
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "timezone": "auto",
                    "forecast_days": max(1, min(days, 16)),
                },
                timeout=self.settings.api_timeout,
            )
            response.raise_for_status()
            daily = (response.json().get("daily") or {}) # 获取每日天气数据，如果没有则使用空字典
            dates = daily.get("time") or []
            codes = daily.get("weather_code") or []
            max_temps = daily.get("temperature_2m_max") or []
            min_temps = daily.get("temperature_2m_min") or []
            rain = daily.get("precipitation_sum") or []

            weather_days = []
            for index, date in enumerate(dates):
                code = codes[index] if index < len(codes) else None
                weather_days.append(
                    DailyWeather(
                        date=date,
                        weather=WEATHER_CODE_TEXT.get(code, f"天气代码 {code}"),
                        min_temperature=min_temps[index] if index < len(min_temps) else None,
                        max_temperature=max_temps[index] if index < len(max_temps) else None,
                        precipitation_sum=rain[index] if index < len(rain) else None,
                    )
                )
            return WeatherResult(
                location=place["name"],
                latitude=place["latitude"],
                longitude=place["longitude"],
                days=weather_days,
            )
        except Exception as exc:
            return WeatherResult(location=location, unavailable=True, message=str(exc))

    def _geocode(self, location: str) -> dict[str, Any]:
        """将地点名称解析为天气接口所需的名称和经纬度。"""
        response = requests.get(
            OPEN_METEO_GEOCODING_URL,
            params={"name": location, "count": 1, "language": "zh", "format": "json"},
            timeout=self.settings.api_timeout,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            raise ValueError(f"没有找到城市：{location}")
        result = results[0]
        display_name = "，".join(part for part in [result.get("name"), result.get("admin1"), result.get("country")] if part)
        return {"name": display_name, "latitude": result["latitude"], "longitude": result["longitude"]}
