import json


ROUTER_SYSTEM_PROMPT = "你是一个严格输出 JSON 的多任务规划器。"


def build_router_prompt(user_input: str, state, available_tools: set[str] | None = None) -> str:
    """结合用户输入和当前状态构建多步骤工具规划提示词。"""
    available_tools = available_tools or {
        "recommend_destination", "plan_itinerary", "refine_itinerary", "estimate_budget",
        "check_weather", "convert_currency", "finalize_plan",
    }
    context = {
        "has_itinerary": bool(getattr(state, "current_itinerary", None)),
        "user_profile": getattr(state, "user_profile", None).model_dump(exclude_none=True)
        if getattr(state, "user_profile", None)
        else {},
        "travel_request": getattr(state, "travel_request", None).model_dump(exclude_none=True)
        if getattr(state, "travel_request", None)
        else {},
    }
    tool_descriptions = {
        "recommend_destination": "推荐旅行目的地",
        "plan_itinerary": "制定新的旅行行程",
        "refine_itinerary": "调整已有行程",
        "estimate_budget": "估算旅行预算",
        "check_weather": "查询天气",
        "convert_currency": "换算货币",
        "finalize_plan": "汇总并导出完整旅行方案",
        "search_poi": "通过地图 MCP 搜索真实地点，arguments 使用 keyword、city 等服务端所需字段",
        "geocode": "通过地图 MCP 将地址解析为坐标，arguments 使用 address、city 等服务端所需字段",
        "plan_route": "通过地图 MCP 查询真实路线，arguments 使用 origin、destination、mode 等服务端所需字段",
    }
    tools_text = "\n".join(
        f"- {name}：{tool_descriptions.get(name, '外部 MCP 工具')}。" for name in sorted(available_tools)
    )
    return f"""
你是 TravelMind 智能旅行规划 Agent 的任务规划器。一个请求可以包含多个任务，请按依赖顺序选择所有必要工具。

可用工具：
{tools_text}

当前状态：{json.dumps(context, ensure_ascii=False)}

规则：
1. steps 可以包含一个或多个工具，但不要添加用户没有要求的任务。
2. 如果预算依赖新行程，先 plan_itinerary 再 estimate_budget。
3. 不要重复同一个工具。
4. confidence 是 0 到 1 的判断把握度，每个步骤和整体都必须给出。
5. 意图不明确或关键条件无法合理补全时，needs_clarification 为 true，并给出简短追问。
6. missing_fields 只填写确实缺少且会阻止执行的字段。
7. current state 中的 user_profile 就是用户已经保存的长期偏好；如果它非空，用户要求“根据以前的偏好”时必须直接使用，不能要求用户重复提供。

只输出 JSON：
{{
  "steps": [
    {{
      "intent": "用户意图",
      "tool_name": "工具名称",
      "reason": "选择原因",
      "confidence": 0.9,
      "requires_existing_itinerary": false,
      "missing_fields": [],
      "depends_on": [],
      "arguments": {{}}
    }}
  ],
  "confidence": 0.9,
  "missing_fields": [],
  "needs_clarification": false,
  "clarification_question": null
}}

用户请求：
{user_input}
"""
