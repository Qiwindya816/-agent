from typing import Any

from schemas.agent_state import AgentState
from schemas.user_profile import UserProfile
from schemas.weather import DailyWeather, WeatherResult
from tools.weather_tool import WeatherTool


class FakeLLMService:
    """为天气工具测试提供可控制的 LLM 响应。"""

    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    def generate_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """返回预设 JSON，或模拟 LLM 调用失败。"""
        if self.error:
            raise self.error
        return self.response or {}


class RecordingWeatherService:
    """记录天气查询参数，并返回固定的无网络天气结果。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def get_forecast(self, location: str, days: int = 7) -> WeatherResult:
        """记录地点和天数，并返回一条模拟天气数据。"""
        self.calls.append((location, days))
        return WeatherResult(
            location=location,
            days=[
                DailyWeather(
                    date="2026-08-10",
                    weather="晴",
                    min_temperature=20,
                    max_temperature=30,
                    precipitation_sum=0,
                )
            ],
        )


def test_weather_tool_prefers_llm_extraction() -> None:
    """LLM 输出有效时，应直接使用其提取的地点和天数。"""
    weather_service = RecordingWeatherService()
    tool = WeatherTool(
        weather_service=weather_service,
        llm_service=FakeLLMService({"location": "上海", "days": 3}),
    )

    result = tool.run({"user_input": "帮我看看魔都这几天要不要带伞", "state": AgentState()})

    assert result.success is True
    assert weather_service.calls == [("上海", 3)]
    assert result.metadata["parameter_extraction"] == "llm"


def test_weather_tool_falls_back_to_rules_when_llm_fails() -> None:
    """LLM 抛出异常时，应使用正则规则提取地点和天数。"""
    weather_service = RecordingWeatherService()
    tool = WeatherTool(
        weather_service=weather_service,
        llm_service=FakeLLMService(error=RuntimeError("LLM unavailable")),
    )

    result = tool.run({"user_input": "查询北京未来3天天气", "state": AgentState()})

    assert result.success is True
    assert weather_service.calls == [("北京", 3)]
    assert result.metadata["parameter_extraction"] == "rules"


def test_weather_tool_uses_profile_destination_when_llm_has_no_location() -> None:
    """LLM 未提取到地点时，应使用用户画像中的目的地。"""
    weather_service = RecordingWeatherService()
    tool = WeatherTool(
        weather_service=weather_service,
        llm_service=FakeLLMService({"location": None, "days": 1}),
    )
    state = AgentState(user_profile=UserProfile(destination="东京"))

    result = tool.run({"user_input": "明天天气怎么样", "state": state})

    assert result.success is True
    assert weather_service.calls == [("东京", 1)]
    assert result.metadata["parameter_extraction"] == "llm"
