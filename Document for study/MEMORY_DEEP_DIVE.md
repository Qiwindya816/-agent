# TravelMind Memory 深度解析：短期记忆、长期记忆与上下文注入

> 本文档以当前工作区代码为准，说明 TravelMind 的 Memory 由哪些部分组成、短期记忆和长期记忆分别如何实现、每项功能使用了什么技术、对应哪部分代码，以及背后的设计原理。
>
> 先给结论：项目中的 Memory 不是一个单独的对象，而是由“图执行状态、会话状态、会话摘要、长期用户画像、可检索长期记忆”共同组成。RAG 是外部知识，不属于用户记忆。

---

## 1. 当前 Memory 的整体组成

```text
用户输入
  │
  ▼
LangGraph 图执行状态 TravelGraphState
  │  保存本轮节点间数据，可由 checkpoint 恢复
  ▼
业务会话状态 AgentState
  ├── chat_history              最近和完整对话历史
  ├── conversation_summary      长对话结构化摘要
  ├── travel_request            当前这一次旅行的约束
  ├── current/structured_itinerary 当前行程
  ├── user_profile              跨旅行稳定画像
  └── active_memories           当前已召回并注入的长期记忆
  │
  ├─────────────── 短期/会话记忆 ───────────────┐
  │                                             │
  ▼                                             ▼
chat_sessions / chat_messages / trips      LangGraph checkpoint
  │                                             │
  │                                             │
  └── 会话恢复、跨轮延续                         └── 图执行恢复、调试和容错

用户输入与历史反馈
  │
  ▼
FeedbackAgent + Profile Extraction
  ├── UserProfile              固定字段长期画像
  └── MemoryCandidate          灵活的长期记忆候选
          │
          ▼
MemoryPipeline
  ├── 校验、敏感信息过滤
  ├── create / merge / defer / reject
  ├── 证据累计与 pending 晋升
  └── Embedding 向量化
          │
          ▼
memory_items + memory_evidence
          │
          ▼
向量/关键词召回 → 冲突消解 → ContextBuilder 注入
```

从生命周期看，可以分为四层：

| 层次 | 主要内容 | 生命周期 | 核心存储 |
|---|---|---|---|
| 图执行记忆 | 当前节点、路由计划、工具结果、错误、执行轨迹 | 一次图调用及其 checkpoint 线程 | LangGraph checkpoint |
| 会话短期记忆 | 对话历史、当前旅行约束、当前行程、摘要 | 当前会话或当前旅行 | `chat_sessions`、`chat_messages`、`trips` |
| 长期用户画像 | 兴趣、旅行风格、住宿/饮食/交通偏好等固定字段 | 跨会话、跨旅行 | `users.user_profile` |
| 可检索长期记忆 | 语义、情景、程序、显式记忆及证据链 | 跨会话，直到删除或过期 | `memory_items`、`memory_evidence`、pgvector |

### 1.1 RAG 为什么不算 Memory

RAG 保存的是景点、攻略、模板、外部资料等“世界知识”，回答“外部世界是什么样”；Memory 保存的是当前用户的偏好、行为和历史，回答“这个用户是什么样”。两者都由 `ContextBuilder` 注入生成上下文，但数据来源、权限边界和更新机制不同。

---

## 2. 短期记忆是怎么实现的

当前项目的短期记忆不是只保存在模型上下文窗口中，而是分为业务会话状态和 LangGraph checkpoint 两套机制。

## 2.1 功能一：保存当前会话的结构化状态

### 怎么实现

`AgentState` 是短期记忆的核心数据结构。它不仅保存聊天记录，还保存当前旅行、当前行程、工具执行结果和最近一次记忆处理结果。

关键字段：

| 字段 | 功能 | 记忆含义 |
|---|---|---|
| `chat_history` | 保存 user/assistant/system 消息 | 多轮对话记忆 |
| `travel_request` | 保存目的地、日期、预算、人数等 | 当前旅行工作记忆 |
| `structured_itinerary` | 保存结构化行程 | 当前任务产物记忆 |
| `conversation_summary` | 保存长对话摘要 | 压缩后的会话记忆 |
| `user_profile` | 加载长期稳定画像 | 长期信息在会话中的快照 |
| `active_memories` | 保存本轮实际选中的长期记忆 | 长期记忆的工作集 |
| `last_intent`、`last_tool_name`、`last_error` | 保存最近执行状态 | 流程连续性与调试信息 |

### 具有哪些功能

- 让下一轮知道上一轮已经确认的旅行条件。
- 支持对已有行程继续修改，而不是重新生成。
- 保存最近的意图、工具、错误和输出版本。
- 在不同 Agent 节点间传递同一个结构化业务状态。
- 通过 Pydantic 校验恢复后的 JSON，避免任意字典在流程中扩散。

### 技术栈与原理

- **Pydantic v2**：用强类型模型定义状态，负责默认值、反序列化和字段校验。
- **结构化状态管理**：把对话中的关键事实从自然语言中抽出，避免完全依赖 LLM 自己“记住”。
- **工作记忆原理**：当前任务需要频繁访问的数据保留在一个可更新状态对象中。

### 对应代码

- [`schemas/agent_state.py`](../schemas/agent_state.py)：`AgentState`、`ChatMessage` 定义。
- [`schemas/travel_request.py`](../schemas/travel_request.py)：当前旅行约束。
- [`multi_agent/state.py`](../multi_agent/state.py)：LangGraph 节点间共享的 `TravelGraphState`。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：各节点读取、更新 `AgentState`。

---

## 2.2 功能二：恢复会话并追加新消息

### 怎么实现

一轮请求进入 `CoordinatorAgent` 后，会先按 `user_id + session_id` 调用 `load_agent_state()` 恢复状态，再把当前用户输入追加到 `chat_history`。最终由 `SummarizerAgent` 追加 assistant 回复并调用 `save_agent_state()` 保存。

```text
CoordinatorAgent
  → load_agent_state(session_id, user_id)
  → chat_history.append(user message)
  → Feedback / Planner / Tool Executor
  → SummarizerAgent
  → chat_history.append(assistant message)
  → save_agent_state(agent_state)
```

数据库是主要事实来源：

- `chat_sessions.agent_state` 保存完整 `AgentState` JSON 快照；
- `chat_messages` 以追加方式保存每条消息；
- `trips.agent_state` 保存当前旅行对应的状态快照；
- `memory_data/users|sessions|trips` 下的 JSON 是迁移和离线回退。

### 具有哪些功能

- 跨 HTTP 请求恢复同一个会话。
- 对话消息只追加，不覆盖既有消息。
- 用 `user_id` 做所有权校验，防止用别人的 `session_id` 读取状态。
- 数据库不可用时，回退到本地 JSON，让本地会话仍能继续。
- JSON 文件使用“临时文件写入后原子替换”，降低文件只写了一半的风险；损坏文件会备份为 `.corrupt`。

### 技术栈与原理

- **SQLAlchemy 2.x**：ORM、事务、自动提交与异常回滚。
- **PostgreSQL / SQLite**：生产持久化与本地测试。
- **JSON/JSONB 思路**：把完整状态快照持久化，便于模型版本化和恢复。
- **Repository Pattern**：将用户隔离、查询和写入放在仓储层。
- **原子写入**：临时文件完成后再替换目标，避免部分写入。
- **Graceful Degradation**：数据库失败时退回 JSON，不让主链路直接中断。

### 对应代码

- [`memory/memory_manager.py`](../memory/memory_manager.py)：数据库优先、JSON 兜底的加载与保存入口。
- [`repositories/agent_state_repository.py`](../repositories/agent_state_repository.py)：状态快照、画像、消息和旅行同步。
- [`repositories/session_repository.py`](../repositories/session_repository.py)：会话和消息的用户隔离访问。
- [`db/models.py`](../db/models.py)：`ChatSession`、`ChatMessage`、`Trip` 数据表。
- [`db/engine.py`](../db/engine.py)：数据库会话和事务边界。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：`CoordinatorAgent` 与 `SummarizerAgent` 的恢复/保存时机。

---

## 2.3 功能三：最近对话窗口

### 怎么实现

`ContextBuilder._format_recent_chat()` 不会把全部聊天历史都塞进 Prompt，而是取：

```python
messages = chat_history[-self.recent_turns:]
```

默认 `MEMORY_RECENT_TURNS=8`。从当前实现看，这个值实际截取的是最后 8 条消息，不是严格的 8 个 user-assistant 对话轮次。

### 具有哪些功能

- 保留最近几条对话的语言指代和局部语境。
- 防止会话越长，Prompt 无限膨胀。
- 让完整历史继续保存在数据库，但只把当前任务需要的一小部分送给模型。

### 技术栈与原理

- **Sliding Window / 滑动窗口**：只保留最近 N 条记录进入工作上下文。
- **Prompt Context Management**：持久化数据和模型本次真正看到的数据分离。
- **Python list slicing**：确定性、低成本地选取尾部消息。

### 对应代码

- [`services/context_builder.py`](../services/context_builder.py)：`_format_recent_chat()`。
- [`config/settings.py`](../config/settings.py)：`memory_recent_turns`。

---

## 2.4 功能四：长对话摘要

### 怎么实现

`ConversationSummarizer` 在消息数达到阈值后生成结构化摘要。`SummarizerAgent` 已经在主流程中调用它：assistant 回复追加后，若 `should_summarize()` 为真，就更新 `agent_state.conversation_summary`。

当前摘要不是调用大模型生成，而是确定性地整理：

- `user_id`、`session_id`、`trip_id`；
- 已确认的 `travel_request`；
- `special_requirements`；
- 当前行程版本；
- 消息数量。

默认 `MEMORY_SUMMARY_AFTER_TURNS=12`，但代码判断的是 `len(chat_history) >= 12`，所以实际是达到 12 条消息时触发，而不是 12 个完整对话轮次。摘要不会删除原始聊天历史，只是多生成一份压缩表示供上下文注入。

### 具有哪些功能

- 在不反复发送完整历史的情况下保留已经确认的约束。
- 为长会话提供一个稳定、低幻觉的摘要。
- 按 `MEMORY_SUMMARY_MAX_TOKENS=800` 做长度上限；超限时按字符数安全截断。

### 技术栈与原理

- **Deterministic Summarization**：从结构化状态生成摘要，不依赖一次新的 LLM 调用。
- **Memory Compression**：把大量历史压成任务所需的关键事实。
- **信息保真优先**：摘要来源是已经校验的状态字段，而不是自由文本推断。

### 对应代码

- [`services/context_builder.py`](../services/context_builder.py)：`ConversationSummarizer`。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：`SummarizerAgent` 中的触发和保存。
- [`config/settings.py`](../config/settings.py)：摘要阈值和最大 token 配置。

---

## 2.5 功能五：按优先级组装本轮上下文

### 怎么实现

`ContextBuilder.build()` 把不同来源的信息包装为 `ContextSection`，按优先级从高到低加入。若某个完整 section 加入后会超过预算，就跳过该 section。

| 优先级 | Section | 内容 |
|---:|---|---|
| 100 | `current_input` | 用户本轮输入 |
| 90 | `travel_request` | 当前旅行约束 |
| 80 | `current_itinerary` | 当前行程版本 |
| 65 | `conversation_summary` | 长对话摘要 |
| 60 | `recent_chat` | 最近消息窗口 |
| 50 | `user_profile` | 固定字段长期画像 |
| 48 | `long_term_memory` | 检索并消解冲突后的长期记忆 |
| 45 | `rag_knowledge` | 外部知识库结果 |
| 40 | extra | 其他补充上下文 |

默认预算是 `MEMORY_MAX_CONTEXT_TOKENS=6000`。当前 token 估算公式为 `ceil(len(text) / 4)`，是近似值，不是模型 tokenizer 的精确 token 数。

### 具有哪些功能

- 确保当前输入和硬约束优先保留。
- 对会话历史、长期记忆和 RAG 统一做预算控制。
- 避免把数据库中的所有信息无差别注入 Prompt。
- 让上下文选择过程可预测、可测试。

### 技术栈与原理

- **Priority Scheduling**：按重要性分配有限上下文预算。
- **Context Window Budgeting**：在 LLM 上下文窗口有限的前提下进行信息选择。
- **Retrieval-then-Inject**：先检索和筛选，再把少量相关内容注入。

### 对应代码

- [`services/context_builder.py`](../services/context_builder.py)：`ContextSection`、`ContextBuilder.build()`。
- [`multi_agent/executor.py`](../multi_agent/executor.py)：把 Memory 和 RAG 检索结果传给 ContextBuilder。

---

## 2.6 功能六：LangGraph checkpoint

### 怎么实现

`build_travel_graph()` 编译状态图时挂载 checkpointer。工作流调用图时，把 `session_id` 作为 LangGraph 的 `thread_id`：

```python
config={"configurable": {"thread_id": self.session_id}}
```

后端选择规则：

- `CHECKPOINT_BACKEND=postgresql` 且 `DATABASE_URL` 以 PostgreSQL 开头：使用 `PostgresSaver`；
- 其他情况：使用 `InMemorySaver`，进程退出后丢失。

### 具有哪些功能

- 保存一次图执行的节点状态和执行结果。
- 可通过同一 `thread_id` 获取已完成的状态。
- 为图执行恢复、中断续跑、调试和节点级可观测性提供基础。

### 技术栈与原理

- **LangGraph StateGraph**：以状态图组织 Coordinator、Feedback、Planner、Tool Executor、Summarizer。
- **LangGraph Checkpoint**：对图状态做快照。
- **psycopg + PostgreSQL**：生产 checkpoint 持久化。
- **Thread Identity**：用 `session_id` 把业务会话与图线程绑定。

### 对应代码

- [`services/checkpoints.py`](../services/checkpoints.py)：PostgreSQL/InMemory checkpointer 选择。
- [`multi_agent/graph.py`](../multi_agent/graph.py)：图拓扑和编译。
- [`multi_agent/workflow.py`](../multi_agent/workflow.py)：`thread_id=session_id`。
- [`tests/integration/test_graph_checkpoint_recovery.py`](../tests/integration/test_graph_checkpoint_recovery.py)：checkpoint 恢复集成测试。

### Checkpoint 与 AgentState 的区别

| 项目 | LangGraph checkpoint | 业务 `AgentState` |
|---|---|---|
| 目的 | 恢复图执行过程 | 恢复产品会话和旅行状态 |
| 内容 | 节点共享状态、计划、工具结果、轨迹 | 用户历史、旅行约束、行程、画像、摘要 |
| 标识 | `thread_id=session_id` | `user_id + session_id` |
| 存储 | LangGraph 自有 checkpoint 表或内存 | 项目业务表和 JSON 兼容存档 |
| 能否互相替代 | 不能 | 不能 |

---

## 3. 长期记忆是怎么实现的

当前项目有两类长期信息：固定字段的 `UserProfile` 和带证据、可语义检索的长期 Memory。前者适合稳定、明确、频繁使用的字段；后者适合开放式偏好、具体经历和协作流程。

## 3.1 长期记忆 A：UserProfile 用户画像

### 怎么实现

`UserProfile` 保存跨旅行稳定的用户偏好：

- `interests`；
- `travel_style`；
- `avoid`；
- `accommodation_preference`；
- `food_preference`；
- `transport_preference`；
- `dietary_restrictions`；
- `mobility_constraints`；
- `visited_destinations`。

目的地、日期、天数、预算等一次性信息属于 `TravelRequest`，不应进入长期画像。`FeedbackAgent` 每轮调用 `extract_profile_updates()`，把更新分别写入 `profile_updates` 和 `trip_updates`。

画像更新支持三类操作：

1. 非空字段覆盖，列表去重合并；
2. `clear_profile_fields` 显式清空整个字段；
3. `remove_profile_items` 从列表中删除指定值。

画像主要存储在 `users.user_profile`，并同步到会话/旅行状态快照和本地 JSON 兼容存档。

### 具有哪些功能

- 快速读取稳定偏好，不需要每次做向量检索。
- 将长期偏好与当前旅行约束分层，防止把“这次预算 3000”误当永久偏好。
- 支持用户纠正、删除和清空旧画像。
- 在规划器和生成上下文中直接使用。

### 技术栈与原理

- **LLM Structured Extraction**：要求模型只输出严格 JSON。
- **Pydantic Schema Validation**：过滤未知字段并验证类型。
- **规则降级**：LLM 不可用时用正则与关键词提取基础信息。
- **Schema-based Memory**：用固定 schema 保存高频、稳定的长期事实。
- **Separation of Concerns**：长期画像与单次旅行状态分离。

### 对应代码

- [`schemas/user_profile.py`](../schemas/user_profile.py)：画像字段和合并/删除逻辑。
- [`schemas/travel_request.py`](../schemas/travel_request.py)：单次旅行字段。
- [`prompts/profile_prompt.py`](../prompts/profile_prompt.py)：长期画像、当前旅行和 Memory 候选的抽取规则。
- [`tools/profile_tool.py`](../tools/profile_tool.py)：LLM 抽取、Pydantic 构造和规则兜底。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：`FeedbackAgent` 应用画像更新。
- [`memory/memory_manager.py`](../memory/memory_manager.py)：画像加载和持久化。

---

## 3.2 长期记忆 B：四类可检索 Memory

| 类型 | 含义 | 例子 | 当前写入策略 |
|---|---|---|---|
| `semantic` | 稳定事实或偏好 | 用户喜欢博物馆 | 置信度达到阈值直接创建，否则 pending |
| `episodic` | 一次具体行为或反馈 | 用户拒绝过夜爬长城 | 当前代码直接创建 |
| `procedural` | 与用户协作的流程偏好 | 每次先给三个候选目的地 | 置信度达到阈值直接创建，否则 pending |
| `explicit` | 用户明确要求记住 | 请记住我不吃辣 | 当前代码直接创建 |

这种分类借鉴了认知科学和 Agent Memory 的常见划分：语义记忆保存一般性事实，情景记忆保存具体经历，程序记忆保存“如何做事”，显式记忆则是产品层增加的高可信用户指令。

核心数据模型：

- `MemoryCandidate`：尚未经过策略判断的候选；
- `MemoryItem`：持久化的长期记忆主体；
- `MemoryEvidence`：支持这条记忆的原始证据；
- `RetrievedMemory`：召回时返回的记忆；
- `MemoryDecision`：冲突消解后的注入决策。

### 对应代码

- [`schemas/memory.py`](../schemas/memory.py)：候选、召回结果、注入决策和写入决策。
- [`db/models.py`](../db/models.py)：`MemoryItem`、`MemoryEvidence` 表模型。

---

## 3.3 功能一：从对话中提取长期记忆候选

### 怎么实现

`FeedbackAgent` 调用 `extract_profile_updates()`。正常路径由 LLM 按 `PROFILE_SYSTEM_PROMPT` 和 `build_profile_prompt()` 返回严格 JSON，其中 `memory_candidates` 只应包含跨旅行有效或值得复盘的信息。

抽取规则明确要求：

- “记住/以后/请记住”使用 `explicit`；
- 稳定偏好使用 `semantic`；
- 接受、拒绝、修改和反馈使用 `episodic`；
- 流程和输出格式偏好使用 `procedural`；
- 单次模糊猜测不生成候选；
- 本次目的地、日期和预算不进入长期 Memory。

LLM 调用失败时进入规则兜底。当前兜底只对“请记住、记住我、以后都、以后请”等显式表达生成 `explicit` 候选，置信度固定为 0.98。

### 具有哪些功能

- 把自由文本转成可校验的 Memory 候选。
- 同时区分画像更新、当前旅行更新和开放式长期记忆。
- LLM 不可用时仍保留用户明确的“记住”指令。

### 技术栈与原理

- **LLM Information Extraction**：从自然语言提取结构化事实。
- **Prompt Contract**：用固定 JSON 输出结构约束模型。
- **Pydantic Validation**：对模型输出做第二次程序校验。
- **Hybrid Extraction**：LLM 主路径 + 正则/关键词兜底。

### 对应代码

- [`prompts/profile_prompt.py`](../prompts/profile_prompt.py)：抽取规则和 JSON 契约。
- [`tools/profile_tool.py`](../tools/profile_tool.py)：`extract_profile_updates()`、`extract_memory_candidates_from_text()`。
- [`multi_agent/nodes.py`](../multi_agent/nodes.py)：`FeedbackAgent` 调用抽取器。

---

## 3.4 功能二：候选校验、隐私过滤和用户开关

### 怎么实现

`MemoryPipeline.ingest_candidates()` 是写入总入口：

1. 检查 `users.long_term_memory_enabled`；
2. 把原始字典解析成 `MemoryCandidate`；
3. 只接受 `semantic/episodic/procedural/explicit`；
4. Pydantic 校验字段、枚举和 0～1 数值范围；
5. 检查敏感词；
6. 交给 `MemoryWritePolicy` 决定 create、merge、defer 或 reject。

当前敏感词标记包括：身份证、护照、银行卡、密码、病历、过敏。命中时拒绝写入 `memory_items`。

需要注意：这是关键词级保护，不是完整的隐私识别模型；同时，“过敏”可能仍作为 `UserProfile.dietary_restrictions` 保存，所以画像和开放式 Memory 的隐私策略目前并不完全统一。

### 具有哪些功能

- 用户可关闭长期记忆写入。
- 非法类型或字段不完整的候选不会落库。
- 明显敏感信息不会进入开放式长期记忆。
- 单条候选失败不会破坏整批流程。

### 技术栈与原理

- **Privacy by Design**：在持久化前过滤，而不是展示时再隐藏。
- **Consent/Feature Flag**：用户级 `long_term_memory_enabled` 开关。
- **Schema Validation**：输入边界校验。
- **Fail-safe**：记忆服务异常不应阻断旅行规划主链路。

### 对应代码

- [`services/memory_pipeline.py`](../services/memory_pipeline.py)：总入口、解析、敏感词和开关。
- [`repositories/user_repository.py`](../repositories/user_repository.py)：用户设置。
- [`db/models.py`](../db/models.py)：`long_term_memory_enabled` 字段。

---

## 3.5 功能三：写入决策、去重和证据累计

### 怎么实现

写入策略先查找同类型、同倾向、同 scope 的相似陈述，再按类型和置信度决定：

```text
发现相似记忆
  → merge：新增 evidence，evidence_count + 1

没有相似记忆
  ├── explicit → create active
  ├── episodic → create active
  ├── semantic 且 confidence >= 0.85 → create active
  ├── procedural 且 confidence >= 0.85 → create active
  └── 低于阈值 → create pending
```

相似陈述检测不是向量去重，而是三层文本规则：

1. 去空格、转小写后完全相同；
2. 去除“用户、我、非常、喜欢、偏好”等词后的 canonical 文本互相包含；
3. `SequenceMatcher` 相似度至少 0.9。

低置信的 semantic/procedural 不会直接丢弃，而是保存为 `pending`。相同证据再次出现时会 merge；当 `evidence_count >= MEMORY_MIN_EVIDENCE_COUNT`（默认 2）后，记忆晋升为 `active` 并补生成 Embedding。

每条 Memory 与 Evidence 分表存储。Evidence 包含来源 `session_id`、`message_id`、`trip_id`、原文、证据类型、置信度和观察时间，形成可追溯证据链。

### 具有哪些功能

- 防止同一偏好重复创建大量记录。
- 保存“为什么系统会记住这件事”的证据。
- 低置信推断需要重复证据后才能进入可召回状态。
- 新证据会更新最高置信度、最高重要度和最近确认时间。

### 技术栈与原理

- **Evidence Accumulation**：通过多次观察提高记忆可信度。
- **Memory Consolidation**：pending 候选在证据足够后晋升 active。
- **Threshold Gating**：用置信度阈值控制长期写入。
- **Fuzzy String Matching**：用规范化、包含关系和 `SequenceMatcher` 做近重复合并。
- **Provenance / 数据血缘**：Memory 与 Evidence 分离，保留来源。

### 对应代码

- [`services/memory_write_policy.py`](../services/memory_write_policy.py)：写入决策和阈值。
- [`services/memory_pipeline.py`](../services/memory_pipeline.py)：执行 create、merge、pending 晋升。
- [`repositories/memory_repository.py`](../repositories/memory_repository.py)：近重复检测、建项、证据累计、激活。
- [`config/settings.py`](../config/settings.py)：置信度阈值和最小证据数。
- [`tests/unit/test_memory_pipeline.py`](../tests/unit/test_memory_pipeline.py)：创建、合并、defer、晋升和敏感信息测试。

---

## 3.6 功能四：向量化与存储

### 怎么实现

active Memory 创建时，以 `statement` 作为 `embedding_text`，通过 `EmbeddingService.embed_query()` 生成向量。默认配置：

| 配置 | 默认值 |
|---|---|
| `EMBEDDING_BASE_URL` | DashScope OpenAI 兼容接口 |
| `EMBEDDING_MODEL` | `text-embedding-v3` |
| `EMBEDDING_DIMENSIONS` | 1024 |
| `EMBEDDING_BATCH_SIZE` | 16 |

PostgreSQL 中使用 `pgvector Vector(1024)`；迁移创建 HNSW 索引并使用 `vector_cosine_ops`。SQLite 不支持 pgvector，ORM 会把 embedding 降级成 JSON，只用于测试和兼容存储。

如果 Embedding API 失败，Memory 仍可保存，只是 `embedding=None`，后续检索走关键词兜底。因此向量服务不是核心业务的单点故障。

### 具有哪些功能

- 把不同措辞但语义接近的查询和记忆匹配起来。
- 预计算记忆向量，查询时只计算用户问题向量。
- 使用 ANN 索引支持规模扩大后的近似最近邻搜索。

### 技术栈与原理

- **OpenAI Python SDK**：调用 OpenAI 兼容 Embedding API。
- **DashScope text-embedding-v3**：默认向量模型。
- **pgvector**：PostgreSQL 向量类型和距离运算。
- **HNSW**：近似最近邻索引，在速度和召回率之间折中。
- **Cosine Similarity**：代码用 `1 - (embedding <=> query_vector)` 转成相似度。

### 对应代码

- [`services/embedding_service.py`](../services/embedding_service.py)：客户端、批量和单条向量化。
- [`db/models.py`](../db/models.py)：`MemoryItem.embedding`。
- [`db/migrations/versions/32934a2e2f05_add_memory_embeddings_and_evidence_.py`](../db/migrations/versions/32934a2e2f05_add_memory_embeddings_and_evidence_.py)：向量列和 HNSW 索引。
- [`services/memory_pipeline.py`](../services/memory_pipeline.py)：写入时生成向量和失败降级。

---

## 3.7 功能五：长期记忆召回

### 怎么实现

`MemoryRetrievalService.retrieve()` 根据数据库能力选择两条路径。

#### PostgreSQL + Embedding 可用

```sql
select memory_id,
       1 - (embedding <=> cast(:vector as vector)) as similarity
from memory_items
where user_id = :user_id
  and status = 'active'
  and embedding is not null
  and (expires_at is null or expires_at > now())
  and (:scope is null or scope = 'global' or scope = :scope)
order by embedding <=> cast(:vector as vector)
limit :top_k
```

- 默认先取最多 8 条；
- 相似度低于 `MEMORY_MIN_RELEVANCE=0.70` 的结果被过滤；
- 可再按 `memory_types` 过滤；
- 查询只允许当前 `user_id`；
- global Memory 可在任何 scope 下使用。

向量召回后还会补一次关键词召回，把历史无向量记录合并进来并按 `memory_id` 去重。

#### SQLite 或 Embedding 不可用

使用元数据/关键词兜底：把查询转小写并按空格拆词，只保留 statement 中包含任一词的 active Memory。这个兜底简单可靠，但中文没有空格时通常会把整句当一个词，召回能力明显弱于向量检索。

### 具有哪些功能

- 根据当前问题只取相关的用户记忆。
- 过滤未激活、已过期、scope 不匹配或相似度过低的记录。
- 向量服务或 PostgreSQL 不可用时仍有基础检索能力。
- 在仓储和 SQL 层强制用户隔离。

### 技术栈与原理

- **Semantic Retrieval**：通过向量距离找语义相关记忆。
- **Metadata Filtering**：同时约束用户、状态、作用域、类型和有效期。
- **Top-K Retrieval**：限制候选数量，控制延迟和 Prompt 体积。
- **Keyword Fallback**：外部向量服务失败时降级。

### 对应代码

- [`services/memory_retrieval.py`](../services/memory_retrieval.py)：向量和关键词两条召回路径。
- [`repositories/memory_repository.py`](../repositories/memory_repository.py)：按用户读取完整 Memory。
- [`config/settings.py`](../config/settings.py)：top-k 和相关度阈值。
- [`scripts/manage_memory.py`](../scripts/manage_memory.py)：命令行搜索入口。

---

## 3.8 功能六：冲突消解和当前输入优先

### 怎么实现

召回结果不会直接全部注入。`MemoryConflictResolver` 为每条记忆计算优先级：

```text
类型基础分
  explicit   100
  semantic    80
  procedural  70
  episodic    60

+ confidence × 5
+ importance × 3
+ scope 精确匹配 10
- scope 不匹配且非 global 5
+ 有 last_confirmed_at 1
```

然后处理两类冲突：

1. **当前输入与历史记忆冲突**：如果当前输入明确出现同一主题且正负倾向相反，当前输入优先，历史记忆被跳过。
2. **历史记忆互相冲突**：同一主题、相反 polarity、scope 兼容时，只保留排序更高的一条。

最后只保留 `MEMORY_INJECTION_TOP_K=5` 条。

### 具有哪些功能

- 防止“用户以前喜欢，但本轮明确不要”时仍强行按旧偏好生成。
- 显式确认过的 Memory 通常高于推断出的情景 Memory。
- 当前 scope 的偏好高于其他非全局 scope。
- 控制最终注入数量。

### 技术栈与原理

- **Rule-based Ranking**：确定性评分，便于解释和测试。
- **Conflict Resolution**：同主题相反倾向互斥。
- **Recency/Confirmation Signal**：最近确认过的记忆略微加权。
- **User Intent Supremacy**：本轮明确输入高于历史推断。

### 对应代码

- [`services/memory_conflict_resolver.py`](../services/memory_conflict_resolver.py)：评分、正负极性和冲突规则。
- [`schemas/memory.py`](../schemas/memory.py)：`MemoryDecision`。
- [`evaluation/memory.py`](../evaluation/memory.py)：错误召回率和冲突解决准确率评测。
- [`tests/unit/test_memory_services.py`](../tests/unit/test_memory_services.py)：冲突优先级测试。

---

## 3.9 功能七：注入 Agent、工具和个性化排序

### 怎么实现

`ToolExecutor.execute()` 在执行生成类工具前完成：

```text
user_input
  → MemoryRetrievalService.retrieve()
  → MemoryConflictResolver.resolve()
  → ContextBuilder.build(memory_results=...)
  → contextual_input
  → tool.run(tool_input)
```

实际注入的 Memory 还会写入 `state.active_memories`，包括类型、陈述、scope、置信度、证据数和选择原因。它们有三种用途：

1. `ContextBuilder` 生成“长期记忆”文本块，供行程生成工具使用；
2. `PersonalizationRankingService` 使用记忆对活动候选做个性化排序；
3. `router_prompt` 会读取 `active_memories` 中已经存在的程序记忆，影响后续规划轮次的工具顺序或输出方式。

当前实现的时序值得注意：本轮 Planner 运行在本轮 Memory 检索之前；Memory 检索发生在 Tool Executor。也就是说，Planner 看到的 `active_memories` 通常来自上一轮已保存状态，而本轮新召回的 Memory 主要影响工具生成上下文和排序。

如果 `personalization_enabled=false`，Tool Executor 不进行长期 Memory 检索与注入，`active_memories` 也会保持为空。

### 具有哪些功能

- 让行程生成使用与当前请求相关的历史偏好。
- 把“为什么选中这条记忆”同步回状态，便于解释和调试。
- 用负面/拒绝类记忆降低不合适活动的排序。
- 用户关闭个性化时停止使用长期记忆。

### 技术栈与原理

- **Retrieval-Augmented Generation for Personal Memory**：检索少量相关用户记忆增强生成。
- **Personalized Ranking**：将偏好作为候选活动排序信号。
- **Explainability**：保存选择理由、置信度和证据数。
- **Feature Toggle**：个性化使用与长期记忆写入分别受不同开关控制。

### 对应代码

- [`multi_agent/executor.py`](../multi_agent/executor.py)：召回、冲突消解、上下文注入和 `active_memories`。
- [`services/context_builder.py`](../services/context_builder.py)：Memory 格式化。
- [`services/personalization_ranking.py`](../services/personalization_ranking.py)：用 Memory 排序活动。
- [`prompts/router_prompt.py`](../prompts/router_prompt.py)：Planner 使用已有 active Memory。
- [`tests/unit/test_memory_injection.py`](../tests/unit/test_memory_injection.py)：注入和个性化开关测试。

---

## 3.10 功能八：用户查看、修改、删除、导出和关闭

### 怎么实现

FastAPI 暴露以下能力：

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/memory` | 按类型/scope 查看 active Memory |
| GET | `/memory/settings` | 查看个性化与长期记忆开关 |
| GET | `/memory/export` | 导出完整 Memory 和 Evidence |
| PATCH | `/memory/{memory_id}` | 修改陈述并重新生成 Embedding |
| DELETE | `/memory/{memory_id}` | 删除单条 |
| DELETE | `/memory` | 清空当前用户全部 Memory |
| POST | `/memory/settings` | 更新两个用户开关 |

前端 `MemoryView.vue` 提供长期记忆管理页面；`scripts/manage_memory.py` 还提供 list、search、update、delete、evidence、clear、export、settings 命令行操作。

两个开关职责不同：

- `long_term_memory_enabled`：控制是否允许新 Memory 写入；
- `personalization_enabled`：控制是否在生成时召回和使用 Memory。

修改 Memory 文本时会尝试重新生成 Embedding；失败仍允许文本修改，向量暂时为空。

### 具有哪些功能

- 用户可以知道系统记住了什么。
- 用户可以纠正错误记忆，而不是只能删除。
- 用户可以导出记忆和证据来源。
- 用户可以分别关闭“继续记住”和“使用记忆个性化”。
- 删除用户时，ORM 级联删除相关 Memory 和 Evidence。

### 技术栈与原理

- **FastAPI**：REST API 和依赖注入。
- **Vue 3 + TypeScript**：Memory 管理 UI。
- **CRUD + Data Portability**：可见、可改、可删、可导出。
- **Right to Control**：把用户控制权放在产品能力中，而不是仅作为后台工具。

### 对应代码

- [`api/memory.py`](../api/memory.py)：Memory REST API。
- [`schemas/api.py`](../schemas/api.py)：请求和响应模型。
- [`frontend/src/views/MemoryView.vue`](../frontend/src/views/MemoryView.vue)：前端管理页。
- [`frontend/src/services/api.ts`](../frontend/src/services/api.ts)：前端 API 封装。
- [`scripts/manage_memory.py`](../scripts/manage_memory.py)：命令行管理工具。
- [`tests/unit/test_memory_control.py`](../tests/unit/test_memory_control.py)：证据、导出、清空、开关和级联删除测试。

---

## 4. 一次完整请求中，短期和长期记忆如何协作

```text
1. 用户发送消息
   └─ MultiAgentTravelWorkflow 以 session_id 作为 thread_id 调用 LangGraph

2. CoordinatorAgent
   ├─ 从业务数据库或 JSON 恢复 AgentState
   └─ 把本轮用户消息加入 chat_history

3. FeedbackAgent
   ├─ LLM/规则抽取 profile_updates
   ├─ 更新本次 travel_request
   ├─ 生成 memory_candidates
   └─ MemoryPipeline 写入、合并或暂存长期 Memory

4. PlannerAgent
   ├─ 读取当前旅行状态、画像
   └─ 可读取状态中已有的 active_memories

5. ToolExecutor
   ├─ 用当前 user_input 召回长期 Memory
   ├─ 冲突消解，只留 top 5
   ├─ ContextBuilder 合并本轮输入、旅行约束、摘要、最近消息、画像、Memory 和 RAG
   ├─ 调用工具生成/修改行程
   └─ 用 Memory 对候选活动排序

6. SummarizerAgent
   ├─ 生成最终回复
   ├─ 追加 assistant 消息
   ├─ 达到阈值时更新 conversation_summary
   └─ 保存 AgentState、消息、旅行状态和 JSON 回退存档

7. LangGraph checkpointer
   └─ 保存本轮图状态，支持按 thread_id 恢复
```

这条链路体现了三种不同的“记住”：

- **短期记住当前在做什么**：`AgentState`、最近消息、当前旅行和摘要；
- **长期记住用户是什么样的人**：`UserProfile`；
- **长期记住与当前问题相关的经历和规则**：`memory_items` + 检索。

---

## 5. 数据库结构与持久化关系

```text
users
  ├── user_profile JSON
  ├── personalization_enabled
  └── long_term_memory_enabled
       │
       ├── chat_sessions
       │     ├── agent_state JSON
       │     ├── user_profile JSON snapshot
       │     └── chat_messages
       │
       ├── trips
       │     ├── agent_state JSON
       │     ├── user_profile JSON snapshot
       │     └── structured_itinerary JSON
       │
       └── memory_items
             ├── statement / structured_value
             ├── type / category / scope / polarity
             ├── confidence / importance / evidence_count
             ├── status / expires_at
             ├── embedding vector(1024)
             └── memory_evidence
                   ├── session_id / message_id / trip_id
                   ├── evidence_text / evidence_type
                   └── confidence / observed_at
```

对应代码：

- [`db/models.py`](../db/models.py)：全部业务表模型。
- [`db/migrations/versions/a4b0c868ef89_create_travelmind_core_tables.py`](../db/migrations/versions/a4b0c868ef89_create_travelmind_core_tables.py)：核心表初始迁移。
- [`db/migrations/versions/edb70f27be69_add_user_profile_snapshot.py`](../db/migrations/versions/edb70f27be69_add_user_profile_snapshot.py)：用户画像快照。
- [`db/migrations/versions/f65880d1a05a_add_agent_state_snapshots.py`](../db/migrations/versions/f65880d1a05a_add_agent_state_snapshots.py)：会话与旅行状态快照。
- [`db/migrations/versions/32934a2e2f05_add_memory_embeddings_and_evidence_.py`](../db/migrations/versions/32934a2e2f05_add_memory_embeddings_and_evidence_.py)：Memory 向量和证据元数据。

---

## 6. 技术栈总表

| 技术 | 在 Memory 中的作用 | 关键代码 |
|---|---|---|
| Python | Memory 业务逻辑和工作流实现 | `services/`、`memory/`、`multi_agent/` |
| Pydantic v2 | 状态、候选、决策和 API 数据校验 | `schemas/` |
| LangGraph | 多节点状态图和 checkpoint | `multi_agent/graph.py`、`services/checkpoints.py` |
| SQLAlchemy 2.x | ORM、Repository、事务 | `db/`、`repositories/` |
| PostgreSQL | 生产业务状态、Memory 和 checkpoint 持久化 | `db/models.py` |
| SQLite | 本地开发和单元测试降级后端 | 测试 fixtures、`DatabaseEngine` |
| pgvector | Memory 向量字段与余弦距离检索 | `MemoryItem.embedding`、`memory_retrieval.py` |
| HNSW | 向量近似最近邻索引 | Memory embedding migration |
| OpenAI Python SDK | 调用 OpenAI 兼容 Embedding API | `services/embedding_service.py` |
| DashScope | 默认 `text-embedding-v3` 服务 | `config/settings.py` |
| FastAPI | Memory 查看、修改、删除、导出和设置 API | `api/memory.py` |
| Vue 3 + TypeScript | 用户侧 Memory 管理界面 | `frontend/src/views/MemoryView.vue` |
| JSON 文件 | 数据库不可用时的兼容/离线回退 | `memory/memory_manager.py` |
| pytest | 写入、召回、冲突、注入、隐私和 checkpoint 验证 | `tests/` |

---

## 7. 原理总表

| 原理 | 本项目中的落地方式 |
|---|---|
| Working Memory | `AgentState` 保存当前会话和旅行状态 |
| Sliding Window | Context 只注入最近 8 条消息 |
| Memory Compression | 12 条消息后生成结构化会话摘要 |
| Structured Memory | `UserProfile` 和 `TravelRequest` 分 schema 保存 |
| Memory Consolidation | pending Memory 在证据数达到 2 后晋升 active |
| Evidence-based Memory | `memory_evidence` 保存每次观察及来源 |
| Confidence Gating | semantic/procedural 默认 0.85 写入阈值 |
| Semantic Retrieval | Embedding + pgvector cosine similarity |
| Metadata Filtering | user、status、scope、type、expires_at 联合过滤 |
| Conflict Resolution | 类型、置信度、重要度、scope 和 polarity 排序消解 |
| Current Intent Priority | 本轮明确输入覆盖历史相反记忆 |
| Context Budgeting | section 优先级 + 6000 token 近似预算 |
| Privacy by Design | 写入前敏感词过滤、用户级开关、Repository 用户隔离 |
| Graceful Degradation | Embedding/数据库故障时使用关键词或 JSON 回退 |
| Observability | `last_memory_result`、`active_memories`、Evidence 和评测指标 |

---

## 8. 当前实现的边界和注意点

以下不是架构目标，而是当前代码的真实行为，阅读或继续开发时需要特别注意。

1. **配置名中的 turns 实际按消息条数计算。** 最近窗口取最后 8 条消息；摘要阈值也是 12 条消息，不是 8/12 个完整 user-assistant 轮次。
2. **摘要不会裁剪原始历史。** `chat_history` 仍完整保存在 `AgentState`；摘要只是额外的压缩上下文。
3. **Context 超预算时按整段跳过。** 当前不会对 section 做智能截断，除摘要自身有字符截断兜底。
4. **关键词召回对中文较弱。** `query.lower().split()` 依赖空格分词，中文整句查询可能难以命中较短 statement。
5. **近重复写入检测不是向量检测。** 当前依赖文本规范化和 `SequenceMatcher >= 0.9`，改写幅度较大时可能重复建项。
6. **敏感信息识别是关键词级。** 覆盖有限，也可能误伤；画像与开放式 Memory 的过滤策略还不完全一致。
7. **explicit/episodic 当前直接 active。** 它们不要求达到 0.85，也不要求两次证据；两次证据规则主要用于低置信 semantic/procedural 的 pending 晋升。
8. **Planner 本轮检索时序在 Tool Executor 之前。** 本轮新召回 Memory 不直接参与同一轮初始路由，主要影响工具上下文和排序。
9. **SQLite 没有真正的向量查询。** embedding 可作为 JSON 保存，但召回会直接走关键词路径。
10. **Checkpoint 不能替代业务数据库。** InMemorySaver 模式下进程退出后 checkpoint 消失，但已保存的 `AgentState` 仍可从业务表/JSON 恢复。

---

## 9. 关键代码阅读顺序

如果要从代码把整条 Memory 链路读懂，建议按以下顺序：

1. [`schemas/agent_state.py`](../schemas/agent_state.py)：先理解会话状态里保存什么。
2. [`schemas/user_profile.py`](../schemas/user_profile.py) 与 [`schemas/memory.py`](../schemas/memory.py)：区分画像和可检索 Memory。
3. [`multi_agent/nodes.py`](../multi_agent/nodes.py)：看一轮请求何时恢复、抽取、写入和保存。
4. [`tools/profile_tool.py`](../tools/profile_tool.py) 与 [`prompts/profile_prompt.py`](../prompts/profile_prompt.py)：看候选如何产生。
5. [`services/memory_pipeline.py`](../services/memory_pipeline.py)：看写入总流程。
6. [`services/memory_write_policy.py`](../services/memory_write_policy.py)：看 create/merge/defer 的判断。
7. [`repositories/memory_repository.py`](../repositories/memory_repository.py)：看去重、Evidence 和数据库操作。
8. [`services/memory_retrieval.py`](../services/memory_retrieval.py)：看向量与关键词召回。
9. [`services/memory_conflict_resolver.py`](../services/memory_conflict_resolver.py)：看冲突排序。
10. [`services/context_builder.py`](../services/context_builder.py)：看短期、长期 Memory 和 RAG 最终如何进入上下文。
11. [`multi_agent/executor.py`](../multi_agent/executor.py)：把检索、注入、工具执行和个性化排序串起来。
12. [`memory/memory_manager.py`](../memory/memory_manager.py) 与 [`repositories/agent_state_repository.py`](../repositories/agent_state_repository.py)：看跨轮持久化与回退。
13. [`api/memory.py`](../api/memory.py) 与 [`frontend/src/views/MemoryView.vue`](../frontend/src/views/MemoryView.vue)：看用户控制面。
14. [`tests/unit/test_memory_pipeline.py`](../tests/unit/test_memory_pipeline.py)、[`tests/unit/test_memory_injection.py`](../tests/unit/test_memory_injection.py)、[`tests/unit/test_memory_control.py`](../tests/unit/test_memory_control.py)：用测试验证理解。

---

## 10. 一句话总结

TravelMind 的短期记忆通过 `AgentState + 最近消息窗口 + 会话摘要 + 业务持久化 + LangGraph checkpoint` 保持当前对话和任务连续；长期记忆通过 `UserProfile + MemoryCandidate + 写入策略 + Evidence 累计 + Embedding/pgvector 召回 + 冲突消解 + Context 注入` 实现跨会话个性化，并由 FastAPI、Vue 和命令行工具提供用户可见、可改、可删、可导出的控制能力。
