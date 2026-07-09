import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

"'定义一个函数来加载环境变量和初始化Deepseek客户端。'"
load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

"''定义一个函数来清理JSON格式的文本。''"
def clean_json(text: str) -> str:
    text = text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "").replace("```", "").strip()
    elif text.startswith("```"):
        text = text.replace("```", "").strip()

    return text

"'定义一个函数来根据用户请求决定使用哪个工具。'"
def decide_tool(user_request: str) -> dict:
    prompt = f"""
你是一个旅游助手 Agent 的任务路由器。

你可以选择以下工具：

1. recommend_destination
用途：当用户还没有明确目的地，希望推荐旅行目的地时使用。

2. plan_itinerary
用途：当用户已经有目的地或明确想要制定行程时使用。

3. estimate_budget
用途：当用户主要关心预算、花费、价格、费用时使用。

请根据用户请求选择最合适的工具。

只输出 JSON，不要输出解释。

JSON 格式：
{{
  "tool_name": "recommend_destination / plan_itinerary / estimate_budget",
  "reason": "选择这个工具的原因"
}}

用户请求：
{user_request}
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一个严格输出 JSON 的任务路由器。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content
    content = clean_json(content)

    return json.loads(content) # 将字符串转化为字典