import re
from types import SimpleNamespace
from typing import Any

from prompts.weather_prompt import WEATHER_QUERY_SYSTEM_PROMPT, build_weather_query_prompt
from schemas.tool import ToolResult
from services.llm_service import LLMService
from services.weather_service import WeatherService
from tools.base import BaseTool


class WeatherTool(BaseTool):
    """实现 天气 能力的统一工具接口。"""
    name = "check_weather"
    description = "查询目的地天气。"

    def __init__(
        self,
        weather_service: WeatherService | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        """初始化天气查询服务和用于参数提取的语言模型服务。"""
        self.weather_service = weather_service or WeatherService()
        self.llm_service = llm_service or LLMService()

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """优先用 LLM 提取地点和天数，失败时使用正则规则兜底。"""
        state = tool_input.get("state")
        user_input = str(tool_input.get("user_input") or "")
        arguments = tool_input.get("mcp_arguments") or {}
        argument_location = arguments.get("location") or arguments.get("city")
        argument_days = arguments.get("days")

        if isinstance(argument_location, str) and argument_location.strip():
            location = argument_location.strip()
            try:
                days = max(1, min(int(argument_days or 7), 16))
            except (TypeError, ValueError):
                days = 7
            extraction_method = "arguments"
            query = None
        else:
            location = None
            days = 7
            query = _extract_query_with_llm(self.llm_service, user_input)

        if location is None and query is None:
            location = _extract_location(user_input)
            days = _extract_days(user_input)
            extraction_method = "rules"
        elif location is None and query is not None:
            location, days = query
            extraction_method = "llm"

        # 本轮未说明地点时优先沿用当前旅行目的地；旧画像字段仅用于兼容 1.x 状态。
        location = location or getattr(getattr(state, "travel_request", None), "destination", None)
        location = location or getattr(getattr(state, "user_profile", None), "destination", None)

        if not location:
            return ToolResult.failure(self.name, "missing_location", "请告诉我要查询哪个城市的天气。")

        weather = self.weather_service.get_forecast(location, days)
        if weather.unavailable:
            return ToolResult.failure(
                self.name,
                "weather_unavailable",
                f"天气服务暂时不可用：{weather.message}",
                retryable=True,
            )
        return ToolResult.ok(
            self.name,
            _format_weather(weather),
            metadata={
                "source": weather.source,
                "parameter_extraction": extraction_method,
                "forecast": weather.model_dump(mode="json"),
            },
        )


def check_weather(travel_request: str, default_location: str | None = None) -> str:
    """以简化接口查询天气，可使用默认目的地作为地点。"""
    profile = SimpleNamespace(destination=default_location)
    state = SimpleNamespace(user_profile=profile)
    result = WeatherTool().run({"user_input": travel_request, "state": state})
    if result.success:
        return str(result.data)
    return result.error.message if result.error else "天气查询失败。"


def _extract_query_with_llm(llm_service: LLMService, text: str) -> tuple[str | None, int] | None:
    """使用 LLM 提取天气参数；调用失败或输出无效时返回 None。"""
    try:
        data = llm_service.generate_json(
            build_weather_query_prompt(text),
            system_prompt=WEATHER_QUERY_SYSTEM_PROMPT,
            temperature=0,
        )
    except Exception:
        return None

    location_value = data.get("location")
    if location_value is not None and not isinstance(location_value, str):
        return None
    location = location_value.strip() if isinstance(location_value, str) else None
    location = location or None

    days_value = data.get("days")
    if days_value is None:
        days = 7
    elif isinstance(days_value, int) and not isinstance(days_value, bool):
        days = max(1, min(days_value, 16))
    else:
        return None

    return location, days


def _extract_location(text: str) -> str | None:
    """使用正则从天气查询文本中提取并清理地点名称。"""
    patterns = [
        r"(?:查询|看看|了解|帮我查|天气|weather|forecast)(?:一下)?\s*([A-Za-z\u4e00-\u9fff\s\-]{1,30})",
        r"([A-Za-z\u4e00-\u9fff\s\-]{1,30})(?:的)?(?:天气|气温|预报)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            location = match.group(1).strip()
            for noise in ["未来", "今天", "明天", "一周", "天气", "weather", "forecast"]:
                location = location.replace(noise, "")
            if location.strip():
                return location.strip()
    return None


def _extract_days(text: str) -> int:
    """从文本提取预报天数，并限制到 1 至 16 天。"""
    match = re.search(r"(\d+)\s*天", text)
    if match:
        return max(1, min(int(match.group(1)), 16))
    if any(word in text for word in ["一周", "本周", "这周"]):
        return 7
    if any(word in text for word in ["今天", "明天", "tomorrow", "today"]):
        return 1
    return 7


def _format_weather(weather) -> str:
    """将结构化天气结果格式化为 Markdown 表格。"""
    lines = [
        f"## {weather.location} 天气预报",
        "",
        f"- 数据源：{weather.source}",
        "",
        "| 日期 | 天气 | 温度 | 降水 |",
        "|---|---|---:|---:|",
    ]
    for day in weather.days:
        lines.append(
            f"| {day.date} | {day.weather} | {day.min_temperature}~{day.max_temperature}°C | {day.precipitation_sum} mm |"
        )
    return "\n".join(lines)
