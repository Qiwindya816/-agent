from pydantic import BaseModel, Field

# 定义天气信息的统一数据结构，包含位置、经纬度、数据源、每日天气列表、不可用标志和消息等信息。
class DailyWeather(BaseModel):
    date: str
    weather: str
    min_temperature: float | None = None
    max_temperature: float | None = None
    precipitation_sum: float | None = None

# 定义每日天气信息的数据结构，里面包含日期、天气描述、最低温度、最高温度和降水总量等字段。
class WeatherResult(BaseModel):
    location: str
    latitude: float | None = None
    longitude: float | None = None
    source: str = "Open-Meteo"
    days: list[DailyWeather] = Field(default_factory=list)
    unavailable: bool = False
    message: str | None = None
