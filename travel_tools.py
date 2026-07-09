import os
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

"'定义一个函数来调用Deepseek旅游助手。'"
def call_llm(prompt: str, system_prompt: str = "你是一个专业的旅游助手。") -> str:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content

"'定义一个函数来根据用户的旅行需求推荐旅游目的地。'"
def recommend_destination(user_profile: str) -> str:
    prompt = f"""
你是一个旅游目的地推荐助手。

请根据用户的旅行需求，推荐 3 个合适的目的地。

输出格式：

## 用户需求理解
简要总结用户的偏好。

## 推荐目的地 1
- 目的地：
- 推荐理由：
- 适合人群：
- 预计花费：
- 建议游玩天数：
- 注意事项：

## 推荐目的地 2
- 目的地：
- 推荐理由：
- 适合人群：
- 预计花费：
- 建议游玩天数：
- 注意事项：

## 推荐目的地 3
- 目的地：
- 推荐理由：
- 适合人群：
- 预计花费：
- 建议游玩天数：
- 注意事项：

用户需求：
{user_profile}
"""
    return call_llm(prompt)

"'定义一个函数来根据用户的旅行需求推荐旅游行程。'"
def plan_itinerary(travel_request: str) -> str:
    prompt = f"""
你是一个旅行行程规划助手。

请根据用户需求，制定一个清晰、合理、不要过度紧凑的旅行行程。

要求：
1. 按天输出
2. 每天包含上午、下午、晚上
3. 说明交通建议
4. 说明餐饮建议
5. 避免安排过满
6. 如果信息不足，基于合理假设制定计划，并说明假设

输出格式：

## 行程概览
- 出发地：
- 目的地：
- 天数：
- 旅行风格：
- 预算倾向：

## 每日行程

### Day 1
- 上午：
- 下午：
- 晚上：
- 交通建议：
- 餐饮建议：

### Day 2
...

## 总体建议
- 住宿区域：
- 交通方式：
- 预算控制：
- 注意事项：

用户需求：
{travel_request}
"""
    return call_llm(prompt)

"''定义一个函数来根据用户的旅行需求估算旅行预算。''"
def estimate_budget(travel_request: str) -> str:
    prompt = f"""
你是一个旅行预算估算助手。

请根据用户的旅行需求，估算旅行预算。

要求：
1. 按类别拆分预算
2. 给出低、中、高三个预算档
3. 说明哪些部分最容易超支
4. 如果没有具体城市或天数，请基于合理假设估算

输出格式：

## 预算估算假设
说明你基于哪些假设估算。

## 预算拆分

| 类别 | 低预算 | 中等预算 | 高预算 |
|---|---:|---:|---:|
| 交通 |  |  |  |
| 住宿 |  |  |  |
| 餐饮 |  |  |  |
| 景点/活动 |  |  |  |
| 市内交通 |  |  |  |
| 购物/备用金 |  |  |  |
| 合计 |  |  |  |

## 预算建议
说明如何控制预算。

用户需求：
{travel_request}
"""
    return call_llm(prompt)