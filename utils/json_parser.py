import json
from typing import Any


class JSONParseError(ValueError):
    """Raised when an LLM response cannot be parsed as JSON."""


def clean_json(text: str) -> str:
    """移除 JSON 文本外层常见的 Markdown 代码围栏。"""
    text = (text or "").strip()

    if text.startswith("```json"):
        return text.replace("```json", "", 1).replace("```", "").strip()

    if text.startswith("```"):
        return text.replace("```", "").strip()

    return text


# 撰写一个函数 parse_json_object(text: str) -> dict[str, Any]，用于从模型响应中解析 JSON 对象。
def parse_json_object(text: str) -> dict[str, Any]:
    """从模型响应中解析 JSON 对象，并校验顶层类型。"""
    cleaned = clean_json(text)

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise JSONParseError(f"Invalid JSON returned by LLM: {exc}") from exc

    if not isinstance(value, dict):
        raise JSONParseError("LLM JSON response must be an object.")

    return value
