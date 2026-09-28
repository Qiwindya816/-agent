import json
from typing import Any

from schemas.itinerary import Itinerary


def build_refine_prompt(current_itinerary: Any, user_feedback: str) -> str:
    """根据现有行程和用户反馈构建结构化修改提示词。"""
    if isinstance(current_itinerary, Itinerary):
        current = current_itinerary.model_dump_json(exclude_none=True)
    else:
        current = str(current_itinerary)
    schema = json.dumps(Itinerary.model_json_schema(), ensure_ascii=False)
    return f"""
你正在修改一份已有的旅行行程。

重要规则：
- 保留原行程中的目的地、旅行天数和有价值的信息。
- 直接根据用户反馈进行调整。
- 不要生成一份与原行程无关的新行程。
- 只输出符合给定 Schema 的完整 JSON 对象，不要输出解释、Markdown 或代码围栏。
- 未经外部服务核验的事实必须保持 unknown，不得虚构 POI、坐标或路线。

当前行程：
{current}

用户反馈：
{user_feedback}

JSON Schema：
{schema}
"""
