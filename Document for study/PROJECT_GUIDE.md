# TravelMind 项目指南

## 1. 项目目标

TravelMind 的目标是完成三项可验证能力：

1. 使用 LangGraph 构建多智能体协作和工具调用，通过 MCP 接入地图、天气和铁路等实时服务。
2. 对官方资料、用户授权攻略和行程模板建立混合 RAG，实现 BM25、向量、地理、模板召回、RRF 和 Reranker。
3. 使用 Checkpoint 与长期记忆支持连续对话、个性化排序和局部重规划。

当前分支 `langgraph-multi-agent-rebuild` 是唯一有效架构。旧原生 Workflow 已移除。

## 2. 运行链路

```text
main.py
  → MultiAgentTravelWorkflow.run_with_state()
  → LangGraph.invoke(thread_id=session_id)
  → coordinator
  → feedback
  → planner
     ├─ 需要澄清 → summarizer
     └─ 可执行   → tool_executor → summarizer
  → 保存会话状态
```

| 模块 | 责任 |
|---|---|
| `multi_agent/state.py` | 定义图中共享的原始状态 |
| `multi_agent/nodes.py` | 实现五类节点及状态读写边界 |
| `multi_agent/graph.py` | 注册节点、边、条件路由和 Checkpointer |
| `multi_agent/workflow.py` | 为 CLI 和未来 API 提供稳定调用入口 |
| `multi_agent/planner.py` | 生成带依赖的工具计划 |
| `multi_agent/executor.py` | 从工具注册表执行步骤 |
| `multi_agent/summarizer.py` | 合并工具结果和错误 |

## 3. 状态设计

`TravelGraphState` 只存节点间需要共享的数据：用户和会话标识、原始输入、业务状态、计划、工具结果、回复、节点轨迹和错误。Prompt 在节点调用时按需构建。

业务状态目前继续使用 `AgentState`，其中区分：

- `UserProfile`：跨旅行长期偏好。
- `TravelRequest`：本次旅行约束。
- `structured_itinerary` 保存经过 Pydantic 校验的 `Itinerary`；`current_itinerary` 是兼容历史存档和展示的 Markdown 视图。
- 预算、天气和汇率结果。
- 聊天历史、工具选择和错误。

行程规划和修改工具已经输出 `Itinerary` JSON；活动具有稳定 ID，并预留 POI、坐标、路线、来源及时效字段。Markdown 由确定性渲染器生成，不再作为新行程的事实源。

## 4. Agent 与工具的边界

Agent 用于具有目标、决策、状态或多步推理的流程责任。地图查询、天气查询、铁路查询、金额求和和路线耗时属于工具或确定性服务。

城市选择、路线优化和预算权衡第一版作为专业能力进入 Tool Executor。只有出现独立循环、私有状态或复杂协商时，才提升为子图。这样可以避免多个业务 Agent 同时覆盖整份行程。

## 5. 数据与错误原则

- 外部事实必须记录 Provider、来源标识、获取时间和有效期。
- 所有工具通过注册表白名单调用并返回 `ToolResult`。
- 网络错误区分超时、限流、鉴权、无结果和服务异常。
- 实时服务失败时不得让 LLM 编造路线、票价、车次或营业信息。
- 当前明确约束优先于长期画像，本次旅行偏好不能自动升级为永久偏好。

## 6. 实现顺序

1. 在现有结构化 `Itinerary` 基础上完成时间/预算校验、结构化版本和基于活动 ID 的局部编辑。
2. 增加 SQLite 开发 Checkpoint 和 PostgreSQL 生产 Checkpoint。
3. 已完成可配置的 MCP Streamable HTTP 客户端和白名单工具适配层；下一步连接实际高德 MCP，核对工具 Schema，并将 POI/路线结果回填行程。稳定后再扩展天气和铁路服务。
4. 建立带来源和删除能力的数据摄取流程。
5. 实现 BM25、向量、地理和模板并行召回以及 RRF。
6. 建立检索测试集后再引入 Reranker。
7. 建立长期记忆条目、证据、冲突、衰减和用户控制。
8. 完成偏好、预算、路线可行性、质量、时效和多样性排序。

具体任务和阶段验收见仓库根目录的 `travel-agent-phased-implementation-plan.md`。

## 7. 运行与测试

```powershell
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q .
```

`tests/unit/test_multi_agent_graph.py` 使用注入的 Planner、Executor 和画像提取器验证完整五节点顺序，不调用真实模型和外部接口。在线模型评测使用 `tests/run_model_evals.py`，运行时会产生 API 用量。

## 8. 当前限制

- 默认 Checkpointer 仍为进程内实现，业务状态由 JSON 仓储跨重启保存。
- 行程规划和修改已经结构化；预算仍主要输出文本，结构化版本、局部编辑和完整确定性校验尚未完成。
- MCP 客户端与白名单适配层已经完成，但尚未配置和验收真实高德 MCP Endpoint，POI/路线结果也尚未自动回填行程。
- 混合 RAG、长期记忆证据和个性化排序尚未完成。
- CLI 输入的 user ID 是本地隔离标识，不是正式认证。

文档必须随实现更新；“计划接入”与“已经实现”始终分开记录。
