from pydantic import BaseModel, Field

# 定义天气信息的统一数据结构，包含位置、经纬度、数据源、每日天气列表、不可用标志和消息等信息。
class DailyWeather(BaseModel):
    """定义 每日、天气 的结构化数据模型。"""
    date: str  # 日期
    weather: str  # 天气
    min_temperature: float | None = None  # 最低温
    max_temperature: float | None = None  # 最高温
    precipitation_sum: float | None = None  # 降水量

# 定义每日天气信息的数据结构，里面包含日期、天气描述、最低温度、最高温度和降水总量等字段。
class WeatherResult(BaseModel):
    """承载 天气 的结构化结果。"""
    location: str  # 地点
    latitude: float | None = None  # 纬度
    longitude: float | None = None  # 经度
    source: str = "Open-Meteo"  # 数据源
    days: list[DailyWeather] = Field(default_factory=list)  # 每日天气
    unavailable: bool = False  # 是否不可用
    message: str | None = None  # 错误信息
