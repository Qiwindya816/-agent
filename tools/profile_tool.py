import re
from typing import Any

from prompts.profile_prompt import PROFILE_SYSTEM_PROMPT, build_profile_prompt
from schemas.travel_request import TravelRequest
from schemas.user_profile import ProfileExtraction, UserProfile
from services.llm_service import LLMService


CHINESE_PROVINCES = {
    "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门",
}


def extract_profile_updates(
    user_input: str,
    *,
    current_profile: UserProfile | None = None,
    current_trip: TravelRequest | None = None,
    chat_history: list[Any] | None = None,
    use_llm: bool = True,
    llm_service: LLMService | None = None,
) -> ProfileExtraction:
    """把本轮文本拆分为长期画像更新和当前旅行更新。"""
    if use_llm:
        try:
            service = llm_service or LLMService()
            data = service.generate_json(
                build_profile_prompt(user_input, current_profile, current_trip, chat_history),
                system_prompt=PROFILE_SYSTEM_PROMPT,
                temperature=0,
            )
            return _build_extraction(data)
        except Exception:
            pass

    return _extract_with_rules(user_input)


def extract_user_profile(user_input: str, *, use_llm: bool = True) -> UserProfile:
    """兼容旧调用：只返回提取结果中的长期画像部分。"""
    return extract_profile_updates(user_input, use_llm=use_llm).profile_updates


def _extract_with_rules(user_input: str) -> ProfileExtraction:
    """在 LLM 不可用时，用正则和关键词拆分长期偏好与本次旅行信息。"""
    text = user_input.strip()
    lower_text = text.lower()
    trip_data: dict[str, Any] = {}
    profile_data: dict[str, Any] = {}

    from_to = re.search(
        r"from\s+([A-Za-z\u4e00-\u9fff\s]+?)\s+to\s+([A-Za-z\u4e00-\u9fff\s]+?)(?:\s+for|\s+in|,|\.|$)",
        text,
        re.IGNORECASE,
    )
    if from_to:
        trip_data["departure_city"] = from_to.group(1).strip()
        trip_data["destination"] = from_to.group(2).strip()

    chinese_destination = re.search(r"(?:去|到|前往)([\u4e00-\u9fff]{2,10}?)(?:旅行|旅游|玩|出差|\d|，|,|。|$)", text)
    if chinese_destination and "destination" not in trip_data:
        trip_data["destination"] = chinese_destination.group(1)

    destination = trip_data.get("destination")
    normalized_destination = str(destination).removesuffix("省").removesuffix("自治区") if destination else ""
    if normalized_destination in CHINESE_PROVINCES:
        trip_data["destination_level"] = "province"
        trip_data["destination_province"] = str(destination)

    days_match = re.search(r"(?:for\s+)?(\d+)\s*(?:days?|天)", lower_text)
    if days_match:
        trip_data["travel_days"] = int(days_match.group(1))

    month_match = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b|(\d{1,2})\s*月",
        lower_text,
    )
    if month_match:
        trip_data["travel_month"] = month_match.group(1).title() if month_match.group(1) else f"{month_match.group(2)}月"

    budget_match = re.search(
        r"(?:budget|预算)?[^\d]*(\d+(?:\.\d+)?)\s*(CNY|JPY|KRW|USD|EUR|GBP|人民币|日元|韩元|美元|欧元|英镑)?",
        text,
        re.IGNORECASE,
    )
    if budget_match and any(word in lower_text for word in ["budget", "预算", "人民币", "cny", "usd", "jpy", "eur", "gbp"]):
        trip_data["budget"] = float(budget_match.group(1))
        if budget_match.group(2):
            trip_data["currency"] = _normalize_currency(budget_match.group(2))

    interest_keywords = {
        "food": ["food", "美食", "吃", "小吃"],
        "city walks": ["city walk", "city walks", "walk", "散步", "城市漫步", "citywalk"],
        "shopping": ["shopping", "购物"],
        "culture": ["culture", "museum", "文化", "博物馆", "历史"],
        "nature": ["nature", "自然", "徒步", "海边", "公园"],
    }
    interests = [
        interest
        for interest, keywords in interest_keywords.items()
        if any(keyword in lower_text for keyword in keywords)
    ]
    if interests:
        profile_data["interests"] = interests

    return ProfileExtraction(
        profile_updates=UserProfile.from_partial_dict(profile_data),
        trip_updates=TravelRequest(**trip_data),
    )


def _build_extraction(data: dict[str, Any]) -> ProfileExtraction:
    """校验并规范化 LLM 返回的分层更新 JSON。"""
    # 兼容旧版扁平输出：长期偏好和单次旅行字段会在这里被重新分流。
    if "profile_updates" not in data and "trip_updates" not in data:
        profile_keys = UserProfile.model_fields.keys()
        trip_keys = TravelRequest.model_fields.keys()
        profile_data = {key: value for key, value in data.items() if key in profile_keys}
        trip_data = {key: value for key, value in data.items() if key in trip_keys}
        data = {"profile_updates": profile_data, "trip_updates": trip_data}

    profile_data = _normalize_profile_data(dict(data.get("profile_updates") or {}))
    trip_data = _normalize_profile_data(dict(data.get("trip_updates") or {}))
    return ProfileExtraction(
        profile_updates=UserProfile.from_partial_dict(profile_data),
        trip_updates=TravelRequest(**{key: value for key, value in trip_data.items() if key in TravelRequest.model_fields}),
        clear_profile_fields=list(data.get("clear_profile_fields") or []),
        clear_trip_fields=list(data.get("clear_trip_fields") or []),
        remove_profile_items=dict(data.get("remove_profile_items") or {}),
        remove_trip_items=dict(data.get("remove_trip_items") or {}),
        start_new_trip=bool(data.get("start_new_trip")),
    )


def _normalize_profile_data(data: dict[str, Any]) -> dict[str, Any]:
    """规范化画像中的列表字段和货币代码。"""
    normalized = dict(data)
    for field in [
        "interests",
        "avoid",
        "dietary_restrictions",
        "mobility_constraints",
        "visited_destinations",
        "special_requirements",
    ]:
        value = normalized.get(field)
        if value is None:
            normalized[field] = []
        elif isinstance(value, str):
            normalized[field] = [item.strip() for item in re.split(r"[,，、;；\s]+", value) if item.strip()]
    if normalized.get("currency"):
        normalized["currency"] = _normalize_currency(str(normalized["currency"]))
    return normalized


def _normalize_currency(value: str) -> str:
    """将中文货币名称或英文别名转换为 ISO 货币代码。"""
    mapping = {
        "人民币": "CNY",
        "日元": "JPY",
        "韩元": "KRW",
        "美元": "USD",
        "欧元": "EUR",
        "英镑": "GBP",
        "RMB": "CNY",
    }
    upper = value.upper()
    return mapping.get(value, mapping.get(upper, upper))


def extract_memory_candidates_from_text(
    user_input: str,
    *,
    session_id: str | None = None,
    trip_id: str | None = None,
) -> list[dict[str, Any]]:
    """Deterministic fallback extraction for explicit long-term memories."""
    text = user_input.strip()
    candidates: list[dict[str, Any]] = []

    if any(phrase in text for phrase in ("请记住", "记住我", "以后都", "以后请")):
        statement = text
        category = "preference"
        if "喜欢" in text:
            category = "interests"
        elif "不要" in text or "不喜欢" in text:
            category = "avoid"
        elif "先" in text and ("预算" in text or "行程" in text):
            category = "workflow"
        candidates.append(
            {
                "memory_type": "explicit",
                "category": category,
                "statement": statement,
                "structured_value": {},
                "scope": "global",
                "polarity": "negative" if any(word in text for word in ("不要", "不喜欢")) else "positive",
                "importance": 0.8,
                "confidence": 0.98,
                "evidence_text": text,
                "evidence_type": "explicit_statement",
                "session_id": session_id,
                "trip_id": trip_id,
            }
        )
    return candidates
