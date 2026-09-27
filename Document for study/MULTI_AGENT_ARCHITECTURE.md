# TravelMind 多智能体架构设计

## 1. 为什么按流程角色划分

本项目采用五类流程角色：主协调、用户反馈、任务规划、工具执行和结果总结。这里的 Agent 表示对状态拥有明确读写责任、能够独立决策的工作流节点，不要求每个节点都调用大模型。

```text
用户输入
  → Coordinator：恢复身份、会话和请求上下文
  → Feedback：更新本次约束、长期偏好，识别新旅行或修改意图
  → Planner：拆解任务，生成步骤、依赖和澄清问题
  → Tool Executor：按白名单和依赖调用能力
  → Summarizer：合并证据、错误和结果，形成回复
```

按流程角色划分的原因：

1. **责任边界稳定。**“规划、执行、总结”不随新增地图或铁路 Provider 改变，工作流拓扑可以长期保持稳定。
2. **状态所有权清楚。**Planner 只产生计划，Executor 只执行，不会出现城市 Agent、路线 Agent 和预算 Agent 同时修改整份行程。
3. **依赖和失败易管理。**路线依赖 POI 坐标，预算依赖行程；统一 Planner 可以显式生成依赖图，Executor 统一处理超时、重试和降级。
4. **减少重复上下文和模型成本。**若每个业务子任务都是自主 Agent，每个 Agent 往往要重复读取用户、日期、预算、画像和前序结果。
5. **更容易测试。**可以分别测试计划是否正确、工具参数是否正确、总结是否忠于工具结果。

## 2. 城市、路线、预算放在哪里

它们没有消失，而是作为“专业能力”进入工具层或受控子图：

| 能力 | 第一版位置 | 升级为专业 Agent/子图的条件 |
|---|---|---|
| 城市选择 | `recommend_destination` 工具，结合 RAG 和排序服务 | 需要多轮候选探索、比较、反思时 |
| 路径规划 | 地图 Provider 工具 + 确定性路线优化服务 | 复杂多城市、时间窗、TSP/VRP 需要迭代求解时 |
| 预算设置 | 预算计算工具和校验器 | 需要多方案谈判、价格搜索与反复权衡时 |
| 天气/铁路 | MCP 工具适配器 | 通常保持工具；它们主要是数据查询而非自主决策 |
| RAG 检索 | 混合检索服务/子图 | 查询改写、并行召回、重排和证据审查足够复杂时 |

判断是否应拆成 Agent 的标准不是“业务名字是否重要”，而是它是否需要独立目标、私有状态、多步推理、循环或与其他角色协商。一次 API 查询、金额求和和路线耗时计算应尽量使用确定性工具。

## 3. 推荐的混合结构

最终结构不是只有五个大节点，也不是每个功能一个 Agent，而是两层结构：

```text
顶层流程 Agent
├─ Coordinator
├─ Feedback
├─ Planner
├─ Tool Executor
│  ├─ destination capability
│  ├─ POI/map capability
│  ├─ route capability
│  ├─ weather MCP capability
│  ├─ railway MCP capability
│  ├─ budget capability
│  └─ hybrid RAG capability
└─ Summarizer
```

当某一能力内部确实出现复杂循环，再把该能力提升为子图。顶层 Planner 仍只看到稳定的业务接口，例如 `search_pois`、`plan_route`、`estimate_budget`，不会耦合高德或某个 MCP 的具体工具名。

## 4. 当前分支状态

分支：`langgraph-multi-agent-rebuild`。

已建立：

- `multi_agent/state.py`：节点共享的原始状态契约。
- `multi_agent/nodes.py`：五类角色实现。
- `multi_agent/graph.py`：LangGraph 拓扑、条件分支和可注入 Checkpointer。
- `multi_agent/workflow.py`：CLI/API 可复用入口，使用 `session_id` 作为 thread ID。
- `main.py`：唯一的 LangGraph 多智能体命令行入口。
- 统一工具注册表仍是唯一执行入口，现有工具继续复用。
- 当前默认使用进程内 Checkpointer；JSON 会话仓储仍负责跨重启业务状态。

## 5. 后续实现批次

1. 将行程改为结构化 `TripPlan`，避免节点间传递 Markdown 作为业务状态。
2. 增加持久化 SQLite 开发 Checkpointer 和 PostgreSQL 生产 Checkpointer。
3. 建立 MCP Gateway：服务健康检查、工具白名单、参数 Schema、统一 `ToolResult`、超时、重试和熔断。
4. 先接地图和天气，再接经过验证的铁路数据服务。
5. 建立公共知识库与用户私有资料隔离的混合 RAG；实现 BM25、向量、地理和模板召回、RRF 与可选 Reranker。
6. 建立长期记忆条目、证据、作用域、置信度、冲突和删除机制。
7. 将偏好、预算、路线、质量、时效和多样性作为可解释特征完成个性化排序。

每一批都必须有离线测试和故障用例。外部实时数据不可用时，回复必须明确标注未知或降级，不能由模型补写车次、票价、路线或营业状态。
