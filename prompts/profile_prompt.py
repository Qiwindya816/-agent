import json
from typing import Any


PROFILE_FIELDS = [
    "interests",
    "travel_style",
    "avoid",
    "accommodation_preference",
    "food_preference",
    "transport_preference",
    "dietary_restrictions",
    "mobility_constraints",
    "visited_destinations",
]

TRIP_FIELDS = [
    "departure_city",
    "destination",
    "destination_level",
    "destination_country",
    "destination_province",
    "destination_city",
    "start_date",
    "end_date",
    "travel_month",
    "travel_dates",
    "travel_days",
    "travelers",
    "budget",
    "currency",
    "interests",
    "travel_style",
    "special_requirements",
]

PROFILE_SYSTEM_PROMPT = "你负责提取用户偏好和本次旅行需求，并且只能返回严格 JSON。"


def build_profile_prompt(
    user_input: str,
    current_profile: Any | None = None,
    current_trip: Any | None = None,
    chat_history: list[Any] | None = None,
) -> str:
    """结合已有记忆和最近对话，构建分层信息更新提示词。"""
    profile_data = current_profile.model_dump(exclude_none=True) if current_profile is not None else {}
    trip_data = current_trip.model_dump(exclude_none=True) if current_trip is not None else {}
    recent_messages = []
    for item in (chat_history or [])[-6:]:
        if hasattr(item, "model_dump"):
            recent_messages.append(item.model_dump())
        elif isinstance(item, dict):
            recent_messages.append(item)

    return f"""
你是 TravelMind 的记忆更新器。请区分“跨旅行长期有效的用户偏好”和“仅属于本次旅行的需求”。

长期画像字段：{PROFILE_FIELDS}
当前旅行字段：{TRIP_FIELDS}

更新规则：
1. 只提取用户本轮明确表达或明确纠正的信息，不要猜测。
2. 目的地、日期、天数、预算属于当前旅行，不能写入长期画像。
3. 用户只说省份时，destination 保存省名，destination_province 保存省名，destination_level 设为 province；不要虚构城市。
4. 普通新增值写入 profile_updates 或 trip_updates。
5. 用户明确要求忘记、删除或不再保留某字段时，把字段名放入对应 clear_*_fields。
6. 用户只删除列表中的某一项时，写入对应 remove_*_items，例如 {{"interests": ["购物"]}}。
7. 用户明确表示“新旅行、另一次旅行、换一个旅行计划”时设置 start_new_trip=true；普通纠正目的地不算新旅行。
8. 未知普通字段用 null，未知列表字段用 []；currency 使用 ISO 代码。

当前长期画像：
{json.dumps(profile_data, ensure_ascii=False)}

当前旅行需求：
{json.dumps(trip_data, ensure_ascii=False)}

最近对话：
{json.dumps(recent_messages, ensure_ascii=False)}

只输出以下结构的 JSON：
{{
  "profile_updates": {{}},
  "trip_updates": {{}},
  "clear_profile_fields": [],
  "clear_trip_fields": [],
  "remove_profile_items": {{}},
  "remove_trip_items": {{}},
  "start_new_trip": false
}}

用户本轮输入：
{user_input}
"""
