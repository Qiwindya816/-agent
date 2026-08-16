WEATHER_QUERY_SYSTEM_PROMPT = "你负责提取天气查询参数，并且只能返回严格 JSON。"


def build_weather_query_prompt(user_input: str) -> str:
    """构建从用户输入中提取天气地点和预报天数的提示词。"""
    return f"""
请从用户的天气查询中提取结构化参数。

规则：
- 只输出 JSON，不要输出解释文字。
- location：城市或地区名称；用户没有明确提供时使用 null，不要猜测。
- days：预报天数，必须是 1 到 16 的整数；没有说明时使用 null。
- “今天”或“明天”按 1 天处理，“一周”“本周”或“这周”按 7 天处理。
- 不要把“天气”“预报”“未来”等非地点词放入 location。

输出格式：
{{
  "location": null,
  "days": null
}}

用户输入：
{user_input}
"""
