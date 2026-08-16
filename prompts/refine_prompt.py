def build_refine_prompt(current_itinerary: str, user_feedback: str) -> str:
    """根据现有行程和用户反馈构建行程修改提示词。"""
    return f"""
你正在修改一份已有的旅行行程。

重要规则：
- 保留原行程中的目的地、旅行天数和有价值的信息。
- 直接根据用户反馈进行调整。
- 不要生成一份与原行程无关的新行程。
- 在结尾说明你具体修改了哪些内容。

当前行程：
{current_itinerary}

用户反馈：
{user_feedback}
"""
