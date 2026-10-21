# TravelMind Context 管理深度解析：状态、检索、预算与 Prompt 注入

> 本文档以当前工作区代码为准，说明 TravelMind 的 Context 由哪些部分组成、每一层如何构建和传递、具有什么功能、使用了哪些技术栈和设计原理，以及对应项目中的哪些代码。
>
> 先给结论：Context 管理不是“把聊天记录拼进 Prompt”这么简单。当前项目同时管理请求身份、图执行状态、业务会话状态、规划器上下文、工具输入上下文和最终回复上下文。真正送给生成模型的内容，只是持久化状态中经过抽取、检索、排序、格式化和预算筛选的一部分。

---

## 1. Context 管理整体组成

```text
HTTP / CLI 用户输入
  │
  ├── 请求身份上下文
  │     user_id / session_id / request_id / 日志 trace
  │
  ▼
TravelGraphState
  │  本轮图执行上下文
  │  route_plan / tool_results / node_trace / errors
  │
  ▼
AgentState
  │  跨轮业务上下文
  │  travel_request / itinerary / chat_history / summary / profile / active_memories
  │
  ├── Feedback 抽取上下文
  │     当前输入 + 当前画像 + 当前旅行 + 最近 6 条历史消息
  │
  ├── Planner 路由上下文
  │     当前输入 + 可用工具 + has_itinerary + profile + trip + active_memories
  │
  └── Tool Executor 生成上下文
        当前输入
        + 当前旅行约束
        + 当前行程版本
        + 会话摘要
        + 最近 8 条消息
        + 用户画像
        + 检索出的长期 Memory
        + 检索出的 RAG 知识
              │
              ▼
        优先级排序 + 近似 token 预算
              │
              ▼
        contextual_input
              │
              ├── LLM 生成工具：进入领域 Prompt
              ├── 确定性工具：主要读取 state / route.arguments
              └── MCP 工具：主要读取结构化 mcp_arguments

工具执行结果
  │
  ├── 更新 AgentState，供后续工具步骤使用
  └── ResponseGenerator 确定性合并为最终回复
```

从职责上，当前 Context 可以分为六层：

| 层次 | 主要内容 | 主要消费者 | 生命周期 |
|---|---|---|---|
| 请求上下文 | 用户、会话、请求 ID、日志字段 | API、中间件、工作流入口 | 一次 HTTP/CLI 请求 |
| 图执行上下文 | 路由计划、工具结果、错误、节点轨迹 | LangGraph 节点 | 一次图调用，可 checkpoint |
| 业务状态上下文 | 当前旅行、行程、历史、画像、摘要 | 所有 Agent 和工具 | 跨多轮会话 |
| 抽取上下文 | 当前输入、旧画像、旧旅行、最近历史 | Feedback LLM | 一次偏好/约束抽取 |
| 规划上下文 | 当前输入、可用工具、结构化状态 | Planner LLM | 一次路由规划 |
| 生成上下文 | 优先级筛选后的状态、Memory、RAG | 行程/目的地/预算生成工具 | 每个工具调用 |

---

## 2. Context 与 Memory、RAG、State 的区别

| 概念 | 回答的问题 | 是否持久化 | 是否直接送给 LLM |
|---|---|---|---|
| State | 系统目前知道和正在处理什么 | 是 | 不一定 |
| Memory | 用户过去有哪些稳定偏好、经历和流程习惯 | 是 | 检索后才注入 |
| RAG | 外部资料中有哪些与当前问题相关的知识 | 是 | 检索后才注入 |
| Context | 本轮某个组件实际能看到的信息集合 | 通常不单独持久化 | 是或被确定性代码消费 |
| Prompt | 对模型的具体指令和内容包装 | 通常不持久化 | 是 |

可以用一个公式理解：

```text
Context = Select(State, Memory, RAG, Current Input, Tool Results)

Prompt = Instructions + Formatted Context + Output Contract
```

因此，数据库里有数据不等于模型本轮能看到它；只有被选中、格式化并进入相应 Prompt 的信息才构成本轮模型 Context。

---

## 3. 功能一：请求身份与可观测性上下文

### 怎么实现

FastAPI 从 `X-User-ID` 请求头取得当前用户；未提供时，本地开发默认使用 `default_user`。消息 API 的 URL 中携带 `session_id`，在执行工作流之前先验证该会话属于当前用户。

中间件还会读取或生成 `request_id`，并把以下字段绑定到结构化日志上下文：

- `request_id`；
- `user_id`；
- `session_id`；
- `trip_id`。

工作流入口继续生成本轮 `request_id`，把 `user_id`、`session_id`、`request_id` 和原始输入放入 LangGraph 初始状态。

### 具有哪些功能

- 确定这次请求属于哪个用户和会话。
- 阻止用户仅凭别人的 `session_id` 读取或继续其上下文。
- 分别为 API 日志和图执行提供请求标识，便于各自追踪。
- 同时支持普通 HTTP 返回和 SSE 流式返回。

### 技术栈与原理

- **FastAPI Dependency Injection**：统一解析当前用户和数据库依赖。
- **HTTP Header Context**：请求头传递用户与追踪信息。
- **Structured Logging / Context Variables**：日志自动携带追踪字段。
- **Tenant Isolation**：`user_id + session_id` 共同约束会话访问。
- **SSE**：异步返回 thinking、message、done 或 error 事件。

### 对应代码

- [`api/dependencies.py`](../api/dependencies.py)：从 `X-User-ID` 解析用户。
- [`api/sessions.py`](../api/sessions.py)：验证会话并启动工作流，提供普通和 SSE 接口。
- [`api/middleware.py`](../api/middleware.py)：请求 ID 和日志上下文。
- [`multi_agent/workflow.py`](../multi_agent/workflow.py)：构造图初始状态。
- [`utils/logger.py`](../utils/logger.py)：结构化日志上下文与敏感信息处理。

---

## 4. 功能二：LangGraph 图执行上下文

### 怎么实现

`TravelGraphState` 是节点之间传递的本轮执行状态。它只保存图编排所需的数据，不直接保存已经格式化好的 Prompt：

| 字段 | 功能 |
|---|---|
| `user_id`、`session_id`、`request_id` | 本轮身份和追踪 |
| `user_input` | 原始用户输入 |
| `agent_state` | 序列化后的业务状态 |
| `route_plan` | Planner 生成的多工具计划 |
| `tool_results` | 每个工具的结构化结果 |
| `needs_clarification` | 是否跳过工具执行直接追问 |
| `node_trace` | 已执行节点序列 |
| `errors` | 工具错误列表 |
| `execution_elapsed_seconds` | 工具执行耗时 |

LangGraph 拓扑固定为：

```text
START
  → coordinator
  → feedback
  → planner
      ├── needs_clarification = true → summarizer
      └── false → tool_executor → summarizer
  → END
```

编译时挂载 checkpointer，调用时使用 `session_id` 作为 `thread_id`。PostgreSQL 配置完整时使用 `PostgresSaver`，否则使用进程内 `InMemorySaver`。

### 具有哪些功能

- 让节点之间只交换结构化状态，而不是共享隐式全局变量。
- 保存路由计划、执行结果、错误和节点轨迹。
- 缺少关键信息时走澄清分支，避免盲目调用工具。
- 支持通过 checkpoint 恢复图状态。

### 技术栈与原理

- **LangGraph StateGraph**：有向状态图和条件边。
- **TypedDict**：定义节点共享状态的轻量类型契约。
- **Checkpointing**：保存图执行快照。
- **Finite-State Workflow**：流程路径由显式节点和条件决定。
- **Separation of Data and Presentation**：图状态不保存已经拼好的 Prompt。

### 对应代码

- [`multi_agent/state.py`](../multi_agent/state.py)：`TravelGraphState`。
- [`multi_agent/graph.py`](../multi_agent/graph.py)：节点拓扑和条件分支。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：每个节点读写哪些状态字段。
- [`services/checkpoints.py`](../services/checkpoints.py)：checkpoint 后端选择。
- [`multi_agent/workflow.py`](../multi_agent/workflow.py)：`thread_id=session_id`。

---

## 5. 功能三：跨轮业务状态上下文

### 怎么实现

`AgentState` 是跨轮 Context 的主要事实来源。它把自然语言会话转换成可复用的结构化状态：

```text
AgentState
  ├── 身份与执行状态
  │     user_id / session_id / request_id / trip_id
  │     current_stage / last_intent / last_tool_names / last_error
  │
  ├── 当前任务状态
  │     travel_request
  │     current_itinerary
  │     structured_itinerary
  │     budget_plan / weather_info / exchange_info
  │
  ├── 对话状态
  │     chat_history
  │     conversation_summary
  │
  └── 个性化状态
        user_profile
        active_memories
        last_memory_result
```

每轮开始时，`CoordinatorAgent` 从数据库或 JSON 回退存档恢复 `AgentState`，随后把当前用户消息追加到 `chat_history`。每轮结束时，`SummarizerAgent` 追加 assistant 回复并保存整个状态。

### 具有哪些功能

- 用户分多轮提供目的地、日期、预算时，系统可以逐步补齐。
- 修改行程时可以直接读取现有结构化行程。
- 生成工具不必重新从全部聊天文本中推断当前旅行状态。
- 恢复会话后继续使用画像、摘要和上轮命中的长期 Memory。

### 技术栈与原理

- **Pydantic v2**：状态结构、默认值和反序列化校验。
- **Stateful Agent**：Agent 的行为由显式状态决定。
- **Schema-first Context**：优先使用结构化字段，而不是反复解析自由文本。
- **Snapshot Persistence**：完整 `AgentState` 以 JSON 快照保存。
- **Repository Pattern**：持久化和用户隔离下沉到仓储层。

### 对应代码

- [`schemas/agent_state.py`](../schemas/agent_state.py)：完整业务状态模型。
- [`schemas/travel_request.py`](../schemas/travel_request.py)：当前旅行约束。
- [`memory/memory_manager.py`](../memory/memory_manager.py)：状态恢复、保存和 JSON 回退。
- [`repositories/agent_state_repository.py`](../repositories/agent_state_repository.py)：数据库状态快照和消息追加。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：Coordinator 恢复与 Summarizer 保存。

---

## 6. 功能四：Feedback 的信息抽取上下文

### 怎么实现

在 Planner 之前，`FeedbackAgent` 先理解“用户本轮输入改变了什么”。调用 `extract_profile_updates()` 时传入：

- 当前 `user_input`；
- 当前 `user_profile`；
- 当前 `travel_request`；
- `chat_history[:-1]`，即不包含刚追加的当前消息的历史。

`build_profile_prompt()` 再从历史中截取最后 6 条消息。当前输入单独放在 Prompt 末尾，因此不会在这个抽取 Prompt 中重复出现。

抽取结果分为：

- `profile_updates`：跨旅行长期画像；
- `trip_updates`：本次旅行约束；
- `clear_*` / `remove_*`：显式清空与删除；
- `start_new_trip`：是否重置当前旅行 Context；
- `memory_candidates`：长期 Memory 候选。

LLM 不可用时，正则和关键词规则提供基础兜底。

### 具有哪些功能

- 将自由文本压缩成结构化 Context。
- 区分“本次旅行”和“跨旅行偏好”。
- 使用有限历史消解“还是三天”“不要那个”等多轮表达。
- 用户开始新旅行时清空旧旅行状态，但保留长期画像。

### 技术栈与原理

- **LLM Structured Extraction**：模型输出严格 JSON。
- **Prompt Contract**：明确字段、更新规则和输出 schema。
- **Context Scoping**：只使用最近 6 条历史，而不是完整聊天。
- **Hybrid Intelligence**：LLM 主路径、正则规则降级。
- **State Reduction**：把冗长自然语言压缩为可复用字段。

### 对应代码

- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：`FeedbackAgent` 的上下文传入和状态更新。
- [`tools/profile_tool.py`](../tools/profile_tool.py)：LLM 调用、规则兜底和输出校验。
- [`prompts/profile_prompt.py`](../prompts/profile_prompt.py)：抽取 Prompt 和最近 6 条历史窗口。
- [`schemas/user_profile.py`](../schemas/user_profile.py)：抽取结果模型。

---

## 7. 功能五：Planner 路由上下文

### 怎么实现

`PlannerAgent` 把当前 `AgentState` 交给 `TravelRouter.route()`。`build_router_prompt()` 不使用完整聊天历史，而是构造一个紧凑的结构化 Context：

```json
{
  "has_itinerary": true,
  "user_profile": {},
  "travel_request": {},
  "long_term_memory": []
}
```

同时还向 Planner 提供：

- 当前部署真正可用的工具列表；
- 每个工具的用途和关键参数说明；
- 当前原始用户请求；
- 工具依赖、缺失字段、澄清和优先级规则。

模型返回 `RoutePlan`，最多 7 个工具步骤。代码随后校验：

- 工具是否在白名单；
- 是否重复；
- 置信度是否在 0～1；
- `depends_on` 是否只指向前置工具名；
- 是否需要已有行程；
- 是否应当向用户追问。

LLM 失败或输出非法时，使用关键词规则路由。

### 具有哪些功能

- 根据当前状态选择一个或多个工具。
- 识别工具依赖，例如先规划行程再估预算。
- 已有画像时，避免重复询问用户已经保存的偏好。
- 缺少已有行程却要求修改时，转为澄清问题。
- MCP 未启用时，不把对应工具暴露给 Planner。

### 技术栈与原理

- **Tool-aware Planning**：Planner 只在可用工具集合中决策。
- **Structured Output**：用 JSON 表示工具计划和依赖图。
- **Whitelist Validation**：模型不能调用未注册工具。
- **Confidence Gating**：整体置信度低于 0.45 时要求澄清。
- **Rule-based Fallback**：模型不可用时仍能识别常见任务。
- **Least Context Principle**：路由只接收做决策所需的结构化摘要。

### 对应代码

- [`multi_agent/planner.py`](../multi_agent/planner.py)：LLM 路由、计划校验、规则降级和顺序修正。
- [`prompts/router_prompt.py`](../prompts/router_prompt.py)：Planner 实际看到的 Context。
- [`schemas/route.py`](../schemas/route.py)：`RouteResult` 和 `RoutePlan`。
- [`tools/registry.py`](../tools/registry.py)：工具注册和可用能力。
- [`tests/unit/test_router.py`](../tests/unit/test_router.py)：多步骤、澄清、画像复用和依赖校验。

### 当前时序说明

Planner 运行在本轮长期 Memory 检索之前。本轮 Planner 看到的 `active_memories` 是从已保存 `AgentState` 恢复的工作集，通常来自上一轮 Tool Executor。当前请求对应的新一轮 Memory 召回发生在 Planner 之后，因此主要影响生成工具，而不直接影响同一轮初始路由。

Planner 也不会直接看到 `conversation_summary`、完整 `chat_history` 或 RAG 结果；它依赖已经抽取进 `travel_request`、`user_profile` 和 `active_memories` 的结构化信息。

---

## 8. 功能六：Memory 与 RAG 的检索上下文

### 怎么实现

每个工具步骤进入 `ToolExecutor.execute()` 后，系统以同一份原始 `user_input` 为查询，分别构建两类检索 Context。

### 8.1 长期 Memory Context

若 `personalization_enabled=true`：

```text
user_input + optional scope
  → MemoryRetrievalService.retrieve()
  → 向量或关键词召回，默认最多 8 条
  → MemoryConflictResolver.resolve()
  → 当前输入冲突覆盖、历史冲突消解
  → 默认最多注入 5 条
```

格式化后每条包含：

- Memory 陈述；
- 类型；
- 置信度；
- 证据数；
- 选择原因。

### 8.2 RAG Context

只有以下工具会触发 RAG：

- `plan_itinerary`；
- `refine_itinerary`；
- `recommend_destination`；
- `estimate_budget`。

查询同时使用：

- 当前 `user_input`；
- `travel_request.destination` 作为 city；
- `travel_request.travel_style` 作为 theme；
- `travel_request.travel_days`。

默认未启用 Rerank 时，RRF 最终最多返回 15 个 chunk；启用 Rerank 时默认保留 6 个。Context 中每个 chunk 包含正文、来源名、URL、发布时间、抓取时间和授权状态。

### 具有哪些功能

- 只把与当前问题相关的长期偏好和外部知识放进 Prompt。
- Memory 在注入前处理正负冲突和本轮输入优先级。
- RAG 保留来源元数据，让生成 Prompt 可以要求模型不编造来源。
- 检索失败时返回空列表，不阻断核心工具执行。

### 技术栈与原理

- **Retrieval-Augmented Context**：先检索，再注入。
- **Embedding + pgvector**：Memory 和 RAG 的语义召回基础。
- **BM25 / Template / Geo / RRF / Rerank**：RAG 多路召回与融合。
- **Metadata Filtering**：按用户、城市、主题、天数和 scope 过滤。
- **Graceful Degradation**：检索异常时降级为空 Context。

### 对应代码

- [`multi_agent/executor.py`](../multi_agent/executor.py)：决定何时检索并把结果交给 ContextBuilder。
- [`services/memory_retrieval.py`](../services/memory_retrieval.py)：长期 Memory 召回。
- [`services/memory_conflict_resolver.py`](../services/memory_conflict_resolver.py)：Memory 冲突消解。
- [`services/rag_retrieval.py`](../services/rag_retrieval.py)：RAG 多路召回、RRF 和可选 Rerank。
- [`services/rerank_service.py`](../services/rerank_service.py)：Rerank API。
- [`services/embedding_service.py`](../services/embedding_service.py)：查询向量生成。

### 当前默认实例化需要注意

默认 `ToolExecutor` 使用 `RagRetrievalService()`，没有传入 `EmbeddingService`。因此 Agent 默认执行路径中的 RAG dense 向量召回不会启动；PostgreSQL 下仍可使用 BM25、模板和其他已满足条件的召回通道。`api/rag.py` 的独立搜索接口会显式注入 `EmbeddingService()`，两条入口的能力目前不完全相同。

---

## 9. 功能七：ContextBuilder 分区与格式化

### 怎么实现

`ContextBuilder.build()` 把不同来源统一包装为只含三个字段的 `ContextSection`：

```python
ContextSection(
    name="current_input",
    content="用户本轮输入：...",
    priority=100,
)
```

当前内置分区如下：

| 优先级 | 分区 | 内容来源 | 格式化方式 |
|---:|---|---|---|
| 100 | `current_input` | 原始用户输入 | 加“用户本轮输入”标签 |
| 90 | `travel_request` | `state.travel_request` | Pydantic dump 后拼接键值 |
| 80 | `current_itinerary` | `state.output_version` | 当前仅写版本号 |
| 65 | `conversation_summary` | `state.conversation_summary` | 直接使用摘要文本 |
| 60 | `recent_chat` | `state.chat_history` | 最近消息拼接为 role:content |
| 50 | `user_profile` | `state.user_profile` | 排除空值和默认值后拼接 |
| 48 | `long_term_memory` | Memory 决策列表 | 陈述、类型、置信度、证据数、原因 |
| 45 | `rag_knowledge` | RAG chunk 列表 | 正文 + 来源元数据 |
| 40 | 动态 extra | 其他调用方参数 | `str(value)` |

空的 Memory/RAG/摘要不会创建相应分区；空画像和空旅行约束会生成“暂无”占位文本。

### 具有哪些功能

- 给异构 Context 建立统一的选择接口。
- 保留来源标签，帮助模型区分当前输入、用户偏好和外部知识。
- 以确定性格式输出，便于测试和调试。
- 允许未来通过 `**extra` 增加新的低优先级 Context。

### 技术栈与原理

- **Dataclass**：轻量、不可变的 Context 分区对象。
- **Context Normalization**：把对象、检索结果和聊天记录统一转为文本分区。
- **Source Attribution**：RAG Context 保留来源和时间信息。
- **Explainable Context**：长期 Memory 带选择原因和证据数。

### 对应代码

- [`services/context_builder.py`](../services/context_builder.py)：全部分区定义和格式化逻辑。
- [`tests/unit/test_context_builder.py`](../tests/unit/test_context_builder.py)：优先级、预算、RAG 来源和 Memory 证据格式测试。

---

## 10. 功能八：最近消息窗口与会话摘要

### 10.1 最近消息窗口

`_format_recent_chat()` 使用：

```python
messages = chat_history[-self.recent_turns:]
```

默认 `MEMORY_RECENT_TURNS=8`。变量名写的是 turns，但当前实际上取最后 8 条消息，而不是 8 个完整 user-assistant 轮次。

由于 `CoordinatorAgent` 已经先把本轮用户输入追加到 `chat_history`，同一条当前输入会同时出现在：

- 优先级 100 的 `current_input`；
- 优先级 60 的 `recent_chat` 最后一条。

也就是说，工具生成 Context 中当前输入存在一次重复。

### 10.2 会话摘要

`ConversationSummarizer` 在 `len(chat_history) >= 12` 时触发。当前摘要是确定性结构化摘要，不调用 LLM，包含：

- 用户、会话和旅行 ID；
- 已确认的 `travel_request`；
- `special_requirements`；
- 当前 `output_version`；
- 消息数量；
- 当前固定为空的 `open_questions`。

摘要上限默认 800 个近似 token。超限时保留开头的 `800 × 4` 个字符。达到阈值后，每一轮都会重新从当前结构化状态生成摘要，不是增量合并，也不会删除原始 `chat_history`。

### 具有哪些功能

- 最近窗口保留语言连贯性和指代关系。
- 摘要保留较早轮次已经沉淀成结构化状态的信息。
- 完整历史仍可用于审计和恢复，Prompt 只取其子集。

### 技术栈与原理

- **Sliding Window**：限制近期自由文本历史规模。
- **Memory Compression**：用摘要替代完整远期对话。
- **Deterministic Summarization**：从结构化状态生成，不增加 LLM 成本和幻觉。
- **Dual Representation**：同一会话同时保留原始消息和压缩摘要。

### 对应代码

- [`services/context_builder.py`](../services/context_builder.py)：最近窗口和 `ConversationSummarizer`。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：回复完成后的摘要触发。
- [`config/settings.py`](../config/settings.py)：8、12、800 等默认值。

---

## 11. 功能九：Context token 预算与优先级选择

### 怎么实现

ContextBuilder 用字符长度近似 token：

```python
estimate_tokens(text) = max(1, ceil(len(text) / 4))
```

分区按 priority 降序排列，再逐段判断：

```text
used = 0
for section in priority descending:
    tokens = estimate(section.content)
    if used + tokens > max_context_tokens:
        跳过整个 section
    else:
        加入 selected
        used += tokens
```

默认 `MEMORY_MAX_CONTEXT_TOKENS=6000`。

### 具有哪些功能

- 在 Context 窗口有限时优先保留本轮输入和当前旅行约束。
- 让摘要、最近历史、画像、Memory 和 RAG 在统一预算中竞争。
- 防止历史记录或检索结果无限增长。
- 算法完全确定，测试中可以构造极小预算验证。

### 技术栈与原理

- **Token Budgeting**：为输入 Context 设定总预算。
- **Priority Scheduling**：高价值信息先占用预算。
- **Greedy Selection**：按顺序贪心加入完整分区。
- **Whole-section Admission**：只接收完整分区，不做局部截断。

### 对应代码

- [`services/context_builder.py`](../services/context_builder.py)：`estimate_tokens()` 和选择循环。
- [`config/settings.py`](../config/settings.py)：`memory_max_context_tokens`。
- [`tests/unit/test_context_builder.py`](../tests/unit/test_context_builder.py)：极小预算测试。

### 当前算法的真实边界

1. **它不是精确 tokenizer。** 对中文按 4 字符约 1 token 估算通常偏乐观，实际模型 token 可能明显更多。
2. **高优先级不是绝对保留。** 如果当前输入本身就超过总预算，`current_input` 会被整个跳过，而不是截断后保留。
3. **不是最优组合搜索。** 算法按优先级贪心选择，不会比较不同分区组合的总信息价值。
4. **没有分区内部预算。** 15 个较长 RAG chunk 会组成一个整体 section；若整体放不下，整个 RAG section 都会被跳过。
5. **只控制输入 Context。** `LLMService.max_tokens` 是可选参数，多数调用没有设置，因此这里不控制模型输出 token。

---

## 12. 功能十：统一 Tool Input 上下文协议

### 怎么实现

Tool Executor 为每个工具构造同一个输入字典：

```python
tool_input = {
    "user_input": user_input,
    "contextual_input": ContextBuilder.build(...),
    "state": state,
    "route": route,
    "mcp_arguments": route.arguments,
}
```

这五个字段代表五种不同的信息形态：

| 字段 | 适合的用途 |
|---|---|
| `user_input` | 解析用户本轮直接表达 |
| `contextual_input` | 交给生成模型的整合文本 |
| `state` | 读取结构化业务状态和当前行程 |
| `route` | 获取意图、阶段、依赖和理由 |
| `mcp_arguments` | 调用外部工具的结构化参数 |

所有工具都收到完整协议，但并非所有工具都会消费所有字段。

### 具有哪些功能

- 为本地 LLM 工具、确定性工具和远端 MCP 工具提供统一接口。
- 让工具按自身性质选择自然语言 Context 或结构化 Context。
- 便于测试工具收到的实际输入。
- 避免把 MCP 参数从长文本中再次解析。

### 技术栈与原理

- **Adapter Pattern**：不同工具适配到统一 `BaseTool.run()`。
- **Typed Result Contract**：所有工具返回 `ToolResult`。
- **Structured Tool Calling**：MCP 使用经过 Planner 生成和本地规范化的 arguments。
- **Raw + Derived Context**：同时保留原始输入和派生 Context。

### 对应代码

- [`multi_agent/executor.py`](../multi_agent/executor.py)：`tool_input` 构造。
- [`tools/base.py`](../tools/base.py)：统一工具接口。
- [`schemas/tool.py`](../schemas/tool.py)：统一成功、失败和 metadata 结构。
- [`tests/unit/test_executor_context.py`](../tests/unit/test_executor_context.py)：验证 ContextBuilder 的输出传入工具。

---

## 13. 不同工具实际消费哪些 Context

“工具收到 Context”与“工具使用 Context”需要分开看。

| 工具类型 | 实际读取 | 是否使用 `contextual_input` |
|---|---|---|
| `plan_itinerary` | `contextual_input` | 是 |
| `recommend_destination` | `contextual_input` | 是 |
| `estimate_budget` | `contextual_input` | 是 |
| `refine_itinerary` | `state.structured_itinerary/current_itinerary` + 原始 `user_input` | 否 |
| `edit_itinerary_activity` | `state.structured_itinerary` + `mcp_arguments` | 否 |
| `check_weather` | `mcp_arguments`、原始输入、`state.travel_request.destination` | 否 |
| `convert_currency` | 原始 `user_input` | 否 |
| 地图/铁路 MCP | `mcp_arguments` | 否 |
| `finalize_plan` | 完整 `state` | 否 |

### 13.1 LLM 生成工具

`plan_itinerary`、`recommend_destination`、`estimate_budget` 优先取 `contextual_input`，没有时才回退到 `user_input`。Context 再被嵌入领域 Prompt：

```text
ContextBuilder 输出
  → build_itinerary_prompt(context)
  → LLMService.generate_json()
```

或：

```text
ContextBuilder 输出
  → build_destination_prompt(context)
  → LLMService.generate_text()
```

### 13.2 行程修改工具

`ItineraryRefineTool` 读取当前结构化行程，但只把原始 `user_input` 作为修改反馈传给 `build_refine_prompt()`。虽然 Tool Executor 为它执行 Memory/RAG 检索并构造 `contextual_input`，当前工具代码没有使用该字段。

### 13.3 实时与确定性工具

天气、汇率、局部编辑和 MCP 工具优先使用结构化参数或 state。这符合“事实工具不应依赖长 Prompt 猜参数”的原则，也减少了 Prompt 注入对外部工具调用的影响。

### 对应代码

- [`tools/itinerary_plan_tool.py`](../tools/itinerary_plan_tool.py)：使用整合 Context 生成结构化行程。
- [`tools/destination_tool.py`](../tools/destination_tool.py)：使用整合 Context 推荐目的地。
- [`tools/budget_tool.py`](../tools/budget_tool.py)：使用整合 Context 估算预算。
- [`tools/itinerary_refine_tool.py`](../tools/itinerary_refine_tool.py)：当前行程 + 原始反馈。
- [`tools/itinerary_edit_tool.py`](../tools/itinerary_edit_tool.py)：结构化行程局部编辑。
- [`tools/weather_tool.py`](../tools/weather_tool.py)：参数、原始输入和旅行目的地回退。
- [`tools/exchange_tool.py`](../tools/exchange_tool.py)：原始输入解析。
- [`tools/mcp_tool.py`](../tools/mcp_tool.py)：结构化 MCP arguments。
- [`tools/export_tool.py`](../tools/export_tool.py)：完整 state 导出。

---

## 14. 功能十一：领域 Prompt 与上下文边界

### 怎么实现

`LLMService` 使用 OpenAI 兼容 Chat Completions 接口，将调用分为两个消息角色：

```text
system message：角色和输出约束
user message：领域 Prompt，其中嵌入格式化 Context
```

不同 Prompt 有不同输出契约：

- Router：严格 JSON 的 `RoutePlan`；
- Profile：严格 JSON 的分层状态更新；
- Itinerary：必须符合 `Itinerary.model_json_schema()`；
- Refine：返回完整新版 Itinerary JSON；
- Destination/Budget：Markdown 文本；
- Weather 参数抽取：严格 JSON。

生成 JSON 后，系统还会使用 `parse_json_object()` 和 Pydantic 模型验证；行程再经过 `ItineraryValidator` 做确定性业务校验。

### 具有哪些功能

- 把“上下文内容”和“模型行为规则”分离。
- 对结构化结果进行程序校验，而不是直接相信模型输出。
- 明确要求未经外部服务核验的事实保持 unknown。
- 要求 RAG 来源只能来自 Context 中实际提供的资料。

### 技术栈与原理

- **OpenAI-compatible Chat Completions**：统一模型调用接口。
- **System/User Role Separation**：系统指令与业务内容分层。
- **JSON Schema**：行程输出结构契约。
- **Pydantic Validation**：运行时类型和字段校验。
- **Deterministic Validation**：时间、预算、结构等由代码再次验证。
- **Grounding**：外部事实要求有检索或工具依据。

### 对应代码

- [`services/llm_service.py`](../services/llm_service.py)：模型调用和 JSON 解析入口。
- [`prompts/router_prompt.py`](../prompts/router_prompt.py)：路由 Prompt。
- [`prompts/profile_prompt.py`](../prompts/profile_prompt.py)：状态抽取 Prompt。
- [`prompts/itinerary_prompt.py`](../prompts/itinerary_prompt.py)：新行程 Prompt 和 JSON Schema。
- [`prompts/refine_prompt.py`](../prompts/refine_prompt.py)：行程修改 Prompt。
- [`prompts/destination_prompt.py`](../prompts/destination_prompt.py)：目的地推荐 Prompt。
- [`prompts/budget_prompt.py`](../prompts/budget_prompt.py)：预算 Prompt。
- [`utils/json_parser.py`](../utils/json_parser.py)：JSON 对象解析。
- [`validators/itinerary_validator.py`](../validators/itinerary_validator.py)：行程业务校验。

---

## 15. 功能十二：多工具计划中的 Context 演进

### 怎么实现

`execute_plan()` 按顺序执行 `RoutePlan.steps`。每一步结束后调用 `after_each`，立即把成功结果写回 `AgentState`：

- 新建/修改行程：更新 `structured_itinerary` 和 Markdown `current_itinerary`；
- 预算：更新 `budget_plan`；
- 天气：更新 `weather_info`；
- 汇率：更新 `exchange_info`；
- 失败：更新 `last_error`。

因此，后续工具能读取前一步更新后的 `state`。依赖未成功时，后续步骤返回 `dependency_failed`；`continue_on_error=true` 时，其他不依赖该失败步骤的工具仍可继续。

地理编码是一个更明确的 Context 传递例子：

```text
geocode 结果
  → execute_plan 暂存 geocode_results
  → _fill_route_arguments()
  → 把坐标填入后续 plan_route.arguments
  → 调用 MCP 路线工具
```

### 具有哪些功能

- 在同一轮中把前置工具结果转换为后续工具可用状态。
- 显式检查依赖，而不是假设前一步一定成功。
- 把自然语言地点逐步转换成路线工具需要的坐标。
- 保留每个步骤的独立 ToolResult 和错误。

### 技术栈与原理

- **Sequential Planning**：按依赖顺序执行工具。
- **State Transition**：每个成功步骤更新业务状态。
- **Dataflow**：前置工具输出成为后续工具输入。
- **Partial Failure Isolation**：单个工具失败不一定终止整个计划。

### 对应代码

- [`multi_agent/executor.py`](../multi_agent/executor.py)：`execute_plan()`、依赖检查和地理编码结果传递。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：`update_after_each()` 状态回填。
- [`schemas/route.py`](../schemas/route.py)：`depends_on` 和 `continue_on_error`。
- [`tools/mcp_tool.py`](../tools/mcp_tool.py)：路线参数规范化。

### 当前跨工具 Context 边界

虽然前一步会更新 `state.structured_itinerary`，但 `ContextBuilder` 的 `current_itinerary` 分区当前只输出 `output_version`，并不输出实际行程正文。`ToolExecutor._build_contextual_input()` 中存在一个会包含完整结构化行程的旧辅助方法，但当前主调用路径没有使用它。

所以“规划行程 → 估算预算”这类多步骤计划中，预算工具收到的 `contextual_input` 不一定包含刚生成的详细行程；它主要看到原始请求、旅行约束和版本号。行程修改工具不受这个问题影响，因为它直接从 `state` 读取当前行程。

---

## 16. 功能十三：最终回复上下文

### 怎么实现

`SummarizerAgent` 的名字容易让人误以为它会把所有结果再次交给 LLM。当前实际行为是：

1. 若 Planner 要求澄清，直接返回 `clarification_question`；
2. 否则把 `tool_results` 反序列化为 `RouteResult + ToolResult`；
3. `ResponseGenerator.generate_many()` 确定性拼接各工具结果；
4. 单个结构化 Itinerary 使用 renderer 转成 Markdown；
5. 多工具结果按标题分节，成功的 `finalize_plan` 不重复展示；
6. 把最终回复追加到 `chat_history`，生成会话摘要并保存状态。

### 具有哪些功能

- 保留每个工具的成功或失败信息。
- 避免再调用一次模型造成事实改写或丢失。
- 结构化行程有统一 Markdown 展示。
- 多任务结果按分节合并。

### 技术栈与原理

- **Deterministic Rendering**：结构化结果由代码转为展示文本。
- **Lossless Aggregation**：尽量不让二次 LLM 总结丢失工具结果。
- **Error Transparency**：失败结果也进入最终回复。
- **Post-turn Persistence**：回复完成后更新历史和摘要。

### 对应代码

- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：`SummarizerAgent`。
- [`multi_agent/summarizer.py`](../multi_agent/summarizer.py)：`ResponseGenerator`。
- [`services/itinerary_renderer.py`](../services/itinerary_renderer.py)：结构化行程渲染。

---

## 17. 一次完整请求中的 Context 生命周期

```text
1. API 接收请求
   ├─ X-User-ID → user_id
   ├─ URL → session_id
   └─ middleware → request/log context

2. Workflow 建立图上下文
   ├─ user_input
   ├─ user_id / session_id / request_id
   └─ thread_id = session_id

3. Coordinator 恢复业务 Context
   ├─ AgentState from DB/JSON
   └─ 当前 user message 加入 chat_history

4. Feedback 压缩自然语言 Context
   ├─ 当前输入
   ├─ 当前画像
   ├─ 当前旅行
   └─ 最近 6 条旧消息
       → profile/trip/memory updates

5. Planner 构建路由 Context
   ├─ current input
   ├─ available tools
   ├─ has_itinerary
   ├─ user_profile
   ├─ travel_request
   └─ previous active_memories
       → RoutePlan

6. 每个 Tool Step 构建执行 Context
   ├─ 召回长期 Memory
   ├─ 生成类工具召回 RAG
   ├─ ContextBuilder 格式化分区
   ├─ 优先级 + token budget
   └─ tool_input 五字段协议

7. 工具消费 Context
   ├─ 生成工具 → contextual_input → Prompt → LLM
   ├─ 确定性工具 → state / arguments
   └─ MCP → mcp_arguments

8. 工具结果回填
   ├─ state 更新
   ├─ 后续依赖工具读取
   └─ tool_results 保存到图状态

9. 最终回复
   ├─ ResponseGenerator 确定性合并
   ├─ assistant message 加入 history
   ├─ 达到阈值时生成 summary
   └─ AgentState 持久化
```

---

## 18. Context 相关配置

| 配置项 | 默认值 | 作用 | 当前实际语义 |
|---|---:|---|---|
| `MEMORY_RECENT_TURNS` | 8 | 最近对话窗口 | 最后 8 条消息 |
| `MEMORY_SUMMARY_AFTER_TURNS` | 12 | 摘要触发阈值 | `chat_history` 达到 12 条消息 |
| `MEMORY_MAX_CONTEXT_TOKENS` | 6000 | 工具生成 Context 总预算 | 字符数除以 4 的近似 token |
| `MEMORY_SUMMARY_MAX_TOKENS` | 800 | 会话摘要上限 | 超限时保留前 3200 字符 |
| `MEMORY_RETRIEVAL_TOP_K` | 8 | Memory 初始召回数 | 冲突消解前候选 |
| `MEMORY_INJECTION_TOP_K` | 5 | Memory 注入数 | 最终进入 Context 的上限 |
| `RAG_RRF_TOP_K` | 15 | 未精排时 RAG 最终数 | 一个 RAG section 中最多 15 条 |
| `RAG_RERANK_TOP_K` | 6 | 精排后 RAG 数 | 开启 Rerank 后最终保留数 |
| `RAG_RERANK_ENABLED` | false | 是否精排 | 默认关闭 |
| `LLM_TEMPERATURE` | 0.3 | 普通生成温度 | JSON 抽取/路由通常显式使用 0 |

对应配置集中在 [`config/settings.py`](../config/settings.py)。

---

## 19. 技术栈总表

| 技术 | 在 Context 管理中的作用 | 关键代码 |
|---|---|---|
| Python | 上下文选择、格式化、流程编排和工具适配 | `services/`、`multi_agent/`、`tools/` |
| Pydantic v2 | AgentState、RoutePlan、ToolResult 和模型输出校验 | `schemas/` |
| LangGraph | 图状态、节点间上下文和 checkpoint | `multi_agent/graph.py` |
| FastAPI | 请求身份、会话 API 和 SSE | `api/` |
| SQLAlchemy | 会话和状态持久化、用户隔离 | `repositories/`、`db/` |
| PostgreSQL / SQLite | 生产状态与本地测试后端 | `db/engine.py` |
| OpenAI Python SDK | DeepSeek/OpenAI-compatible Chat Completions | `services/llm_service.py` |
| DeepSeek compatible API | Router、Profile、行程和文本生成 | `config/settings.py` |
| pgvector / Embedding | Memory 和 RAG 语义检索 | `services/*retrieval.py` |
| BM25 / RRF / Rerank | RAG Context 候选选择和排序 | `services/rag_retrieval.py` |
| MCP | 地图、铁路等结构化外部工具上下文 | `tools/mcp_tool.py` |
| SSE | 向前端推送工作流状态和结果 | `api/sessions.py` |
| pytest | Context 优先级、预算、注入和路由测试 | `tests/unit/` |

---

## 20. 原理总表

| 原理 | 本项目中的落地方式 |
|---|---|
| Stateful Agent | `AgentState` 保存跨轮业务状态 |
| Context Scoping | Feedback、Planner、Tool 各看不同信息子集 |
| Least Context Principle | Planner 不读取完整历史和 RAG |
| Sliding Window | 工具 Context 取最后 8 条消息，抽取 Context 取最后 6 条旧消息 |
| Context Compression | 12 条消息后生成确定性摘要 |
| Retrieval-Augmented Context | Memory 与 RAG 检索后再注入 |
| Priority Scheduling | 分区按 100～40 的优先级选择 |
| Token Budgeting | 6000 个近似 token 的输入预算 |
| Structured Tool Calling | MCP 和局部编辑使用结构化 arguments |
| Prompt Contract | Router/Profile/Itinerary 使用严格 JSON 契约 |
| Validation after Generation | JSON 解析、Pydantic 和业务 Validator 三层校验 |
| Current Input Priority | Memory 冲突时本轮明确要求优先 |
| Graceful Degradation | LLM、Memory、RAG 失败有规则或空结果降级 |
| Tenant Isolation | 会话、Memory 和 RAG 查询绑定 user_id |
| Deterministic Rendering | 最终回复不再由第二个 LLM 自由总结 |
| Observability | request_id、node_trace、errors、tool metadata 和 token usage 日志 |

---

## 21. 当前实现边界与改进方向

以下是基于当前代码能够直接确认的行为。

### 21.1 当前输入在 Tool Context 中重复

Coordinator 已将本轮消息加入 `chat_history`，ContextBuilder 又单独创建 `current_input`，所以当前输入同时出现在两个分区。可以在最近窗口中排除最后一条 user message，减少 token 浪费和重复权重。

### 21.2 token 估算不适合精确控制中文

字符数除以 4 更接近英文粗略估算。若希望严格遵守模型窗口，应使用对应模型 tokenizer，并分别记录 system、user、schema 和输出预留 token。

### 21.3 分区只有“全进或全不进”

单个 RAG 或聊天分区过大时会被整个丢弃。可以为每类 Context 设置独立预算，先在分区内部截断或逐项选择，再做全局组合。

### 21.4 当前行程分区没有实际行程内容

优先级 80 的 `current_itinerary` 目前只有 `output_version`。已有完整结构化行程在 `state` 中，但没有统一进入 `contextual_input`。应根据工具类型决定是否注入行程摘要、关键活动或完整 JSON。

### 21.5 `output_version` 与数据库行程版本不是同一更新链路

`output_version` 主要由导出服务递增；行程版本服务另有 `version_number`。ContextBuilder 使用的是 `state.output_version`，它可能不能代表最近一次行程编辑版本。

### 21.6 行程 Refine 没有消费已构建的 Memory/RAG Context

Executor 会为 `refine_itinerary` 检索 Memory/RAG，但工具只使用原始用户反馈和当前行程。若希望修改过程参考最新知识或长期偏好，需要把 `contextual_input` 传入 `build_refine_prompt()`，同时避免重复嵌入完整行程。

### 21.7 Planner 使用的长期 Memory 可能是一轮前的工作集

本轮检索在 Planner 之后发生。可以把轻量 Memory 检索提前到 Planner，或为 procedural Memory 建立单独的稳定索引，但需要权衡延迟和调用成本。

### 21.8 默认 Agent RAG 未显式启用 dense 召回

`ToolExecutor` 默认创建 `RagRetrievalService()`，没有传入 EmbeddingService。可以统一依赖注入，让 Agent 与独立 RAG API 使用相同检索能力。

### 21.9 Context 来源只是文本标签，没有强信任边界

当前用户文本、历史消息和 RAG chunk 最终都嵌入同一个 user message。虽然有“来源”“当前输入优先”等提示，但没有对外部内容做专门的 prompt-injection 标记、过滤或隔离。可以增加来源可信度、内容引用边界和不执行检索内容指令的系统规则。

### 21.10 摘要字段还不完整

`open_questions` 当前固定为空，`rejected_or_special_requirements` 直接取 `special_requirements`，并不是真正从历史中计算的未解决问题或拒绝记录。若用于长会话压缩，应把这些字段接入真实状态来源。

### 21.11 没有保存实际 prompt token 数

LLMService 会记录供应商返回的 token usage 到日志，但 `chat_messages.token_count` 当前保存消息时没有写入；ContextBuilder 也没有记录每个 section 的实际 token 占用和最终是否被选择。可以增加 Context manifest 便于调试和评测。

### 21.12 存在未使用的旧 Context helper

`ToolExecutor._build_contextual_input()` 会包含完整画像、旅行需求和当前行程，但当前主路径使用 `ContextBuilder.build()`，该 helper 没有调用点。继续演进时应删除它或合并其“完整行程”能力，避免两套实现漂移。

### 21.13 API request ID 与工作流 request ID 尚未贯通

HTTP 中间件会读取或生成一个 `request_id` 用于访问日志，但 `api/sessions.py` 启动工作流时没有把这个 ID 传入 `MultiAgentTravelWorkflow`；工作流会再生成一个新的 `request_id`。因此两者目前是两套标识，不能仅凭 request ID 直接完成端到端日志关联。可以在 `_execute_workflow()` 中显式传递中间件 request ID，并让工作流复用。

---

## 22. Context 测试覆盖

| 测试文件 | 验证内容 |
|---|---|
| [`tests/unit/test_context_builder.py`](../tests/unit/test_context_builder.py) | 优先级、预算、摘要、RAG 来源、Memory 证据格式 |
| [`tests/unit/test_executor_context.py`](../tests/unit/test_executor_context.py) | Executor 把 ContextBuilder 输出交给工具 |
| [`tests/unit/test_memory_injection.py`](../tests/unit/test_memory_injection.py) | 长期 Memory 注入和个性化开关 |
| [`tests/unit/test_router.py`](../tests/unit/test_router.py) | Planner 上下文、已保存偏好和澄清逻辑 |
| [`tests/unit/test_multi_agent_graph.py`](../tests/unit/test_multi_agent_graph.py) | 五节点顺序和图状态结果 |
| [`tests/integration/test_agent_state_repository.py`](../tests/integration/test_agent_state_repository.py) | 会话状态往返和用户隔离 |
| [`tests/integration/test_graph_checkpoint_recovery.py`](../tests/integration/test_graph_checkpoint_recovery.py) | checkpoint 状态恢复 |

当前测试能够证明核心 Context 被构建和注入，但还缺少以下回归测试：

- 中文真实 tokenizer 的预算边界；
- 超大 RAG section 的部分保留策略；
- 多工具计划中前置行程是否真正进入后续预算 Prompt；
- Refine 是否消费 Memory/RAG；
- 当前消息去重；
- Prompt injection 与来源信任边界。

---

## 23. 推荐代码阅读顺序

1. [`multi_agent/state.py`](../multi_agent/state.py)：先理解本轮图 Context。
2. [`schemas/agent_state.py`](../schemas/agent_state.py)：理解跨轮业务 Context。
3. [`multi_agent/graph.py`](../multi_agent/graph.py)：看 Context 在节点间如何流动。
4. [`multi_agent/nodes.py`](../multi_agent/nodes.py)：看每个节点读取和更新什么。
5. [`tools/profile_tool.py`](../tools/profile_tool.py) 与 [`prompts/profile_prompt.py`](../prompts/profile_prompt.py)：看自然语言如何压缩成状态。
6. [`prompts/router_prompt.py`](../prompts/router_prompt.py) 与 [`multi_agent/planner.py`](../multi_agent/planner.py)：看 Planner 的最小 Context。
7. [`multi_agent/executor.py`](../multi_agent/executor.py)：看 Memory/RAG 检索和统一 Tool Input。
8. [`services/context_builder.py`](../services/context_builder.py)：看分区、格式化、优先级和预算。
9. [`tools/itinerary_plan_tool.py`](../tools/itinerary_plan_tool.py)、[`tools/itinerary_refine_tool.py`](../tools/itinerary_refine_tool.py)、[`tools/mcp_tool.py`](../tools/mcp_tool.py)：比较不同工具如何消费 Context。
10. [`services/llm_service.py`](../services/llm_service.py) 与 [`prompts/`](../prompts)：看 Context 如何进入模型消息。
11. [`multi_agent/summarizer.py`](../multi_agent/summarizer.py)：看结果如何确定性合并。
12. [`memory/memory_manager.py`](../memory/memory_manager.py) 与 [`repositories/agent_state_repository.py`](../repositories/agent_state_repository.py)：看 Context 如何跨轮保存。
13. [`tests/unit/test_context_builder.py`](../tests/unit/test_context_builder.py) 与 [`tests/unit/test_executor_context.py`](../tests/unit/test_executor_context.py)：用测试验证理解。

---

## 24. 一句话总结

TravelMind 的 Context 管理通过 `请求身份 → LangGraph 图状态 → AgentState 业务状态 → Feedback 结构化抽取 → Planner 最小路由上下文 → Memory/RAG 检索 → ContextSection 优先级与 token 预算 → 统一 Tool Input → 工具状态回填 → 确定性结果汇总` 形成完整链路；核心思想是让不同组件只看到完成当前职责所需的信息，并用结构化状态、检索、预算和校验控制 LLM 的输入边界。
