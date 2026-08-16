# TravelMind 模型评测说明

## 评测内容

`model_eval_cases.json` 包含四类样例：

- `router`：意图识别和工具选择；
- `profile`：用户画像字段提取及防止无依据补全；
- `weather`：天气地点和天数提取；
- `manual`：目的地、行程、修改和预算等生成质量，需要人工评分。

结构化样例可自动评分，人工样例通过每条记录中的 `criteria` 检查。

## 运行方法

先确认 `.env` 中配置了有效的 `DEEPSEEK_API_KEY`。评测会实际调用模型并产生 API 用量。

先运行少量样例：

```powershell
D:\Anoconda\envs\agent_env\python.exe tests\run_model_evals.py --limit 3
```

按组件运行：

```powershell
D:\Anoconda\envs\agent_env\python.exe tests\run_model_evals.py --component router
D:\Anoconda\envs\agent_env\python.exe tests\run_model_evals.py --component profile
D:\Anoconda\envs\agent_env\python.exe tests\run_model_evals.py --component weather
```

运行全部结构化样例：

```powershell
D:\Anoconda\envs\agent_env\python.exe tests\run_model_evals.py
```

默认报告写入：

```text
outputs/model_eval_report.json
```

## 如何分析问题

优先按组件查看通过率，然后检查报告中 `passed=false` 的记录：

1. `actual` 与期望语义一致但格式不同：改进输出规范、字段归一化或评分规则；
2. 模型遗漏明确信息：补充提示词字段说明和正反示例；
3. 模型编造未提供的信息：加强“未知使用 null/[]”规则；
4. 多次运行结果不稳定：固定 `temperature=0`，并增加重复运行统计；
5. 多意图请求只完成一项：工作流需要支持任务拆分或多工具计划；
6. 生成内容事实可疑：增加真实 API、知识检索或结果校验，不能只改提示词。

## 当前代码中值得重点验证的改进点

- `UserProfile` 已包含交通偏好、饮食限制、行动限制和已访问地点，但画像提示词字段列表尚未完整覆盖；
- 路由器一次只选择一个工具，多意图请求可能丢失预算、天气等次要任务；
- `confidence` 和 `missing_fields` 尚未真正驱动追问或流程控制；
- 行程与预算由模型直接生成 Markdown，目前没有转换为结构化模型并执行校验；
- 路由和画像模块会静默回退规则，正式评测时应区分“模型成功”和“规则兜底”；
- 正则兜底适合常见句式，但对城市别称、隐含地点和复杂时间表达能力有限。
