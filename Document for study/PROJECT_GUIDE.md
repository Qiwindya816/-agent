# TravelMind 项目设计、版本迭代与学习指南

> 文档定位：这是 TravelMind 的长期项目档案。用于快速理解系统、记录版本演进、复盘设计决策，并把项目经验转化为 Python/LLM Agent 岗位的面试能力。

## 1. 一眼看懂项目

### 1.1 项目是什么

TravelMind 是一个命令行智能旅行规划 Agent。它通过用户 ID 区分本地用户，把长期偏好与当前旅行分开维护，通过 LLM 生成带置信度的多步骤计划，再调用一个或多个工具完成目的地推荐、行程规划、预算估算、天气查询、汇率换算和版本化方案导出。

当前默认模型：

```text
deepseek-v4-flash
```

### 1.2 当前技术栈

| 类别 | 当前实现 |
|---|---|
| 语言 | Python 3.11/3.12 兼容目标 |
| 数据模型 | Pydantic v2、pydantic-settings |
| LLM SDK | OpenAI Python SDK，连接 DeepSeek OpenAI-compatible API |
| 天气数据 | Open-Meteo |
| 汇率数据 | Frankfurter |
| 持久化 | 本地 JSON 文件 |
| 测试 | pytest |
| 日志 | Python `logging` |
| 当前界面 | 命令行 CLI |

### 1.3 核心架构

```text
用户
  ↓
main.py                         命令行输入
  ↓
TravelWorkflow                 编排一次完整请求
  ├─ Profile Extraction        提取并合并用户画像
  ├─ TravelRouter              判断意图、选择工具
  ├─ ToolExecutor              从注册表获取工具实例
  ├─ BaseTool.run()            执行业务工具
  │    ├─ LLMService           文本/JSON 模型调用
  │    ├─ WeatherService       真实天气 API
  │    ├─ ExchangeService      真实汇率 API
  │    └─ ExportService        Markdown 导出
  ├─ ResponseGenerator         ToolResult 转用户回复
  └─ MemoryManager             保存用户画像和会话状态
```

### 1.4 最重要的设计原则

1. **LLM 负责理解和生成，不负责伪造实时事实。** 天气和汇率必须来自真实 API。
2. **Workflow 负责编排，Tool 负责业务，Service 负责外部资源。**
3. **不把所有逻辑写进 `main.py`。** 入口只处理输入输出。
4. **所有工具返回统一的 `ToolResult`。** 成功和失败结构一致。
5. **关键 LLM 任务有确定性兜底。** 路由、画像和天气参数提取都有规则回退。
6. **数据通过 Schema 明确约束。** Pydantic 模型承担 DTO、验证和序列化职责。

## 2. 当前版本状态

| 项目项 | 状态 | 说明 |
|---|---|---|
| CLI 对话 | 已实现 | `main.py` |
| 用户画像提取 | 已实现 | LLM 优先、规则兜底 |
| 单工具路由 | 已实现 | LLM 优先、关键词兜底 |
| 工具注册表 | 已实现 | 7个内置工具 |
| 目的地推荐 | 已实现 | LLM 生成 Markdown |
| 行程规划/修改 | 已实现 | LLM 生成 Markdown |
| 预算估算 | 已实现 | LLM 生成 Markdown |
| 天气查询 | 已实现 | LLM 提参、规则兜底、Open-Meteo 查数据 |
| 汇率换算 | 已实现 | 规则提参、Frankfurter 查数据 |
| 用户/会话持久化 | 已实现 | 输入用户 ID、新会话 ID、本地 JSON、原子写入 |
| Trip 仓储 | 已实现基础同步 | 当前旅行随会话同步到 TripState |
| Validator | 仅部分准备 | 类已定义，主流程尚未调用 |
| 多工具计划 | 已实现 | RoutePlan、依赖顺序、逐步状态回写 |
| 多用户/多会话 | 已实现本地原型 | 用户输入 ID，每次启动创建新会话 |
| RAG/Multi-Agent | 未实现 | 属于后续阶段 |
| Web 前端/API | 未实现 | 当前只有 CLI |

## 3. 一次请求的完整执行流程

### 3.1 CLI 接收输入

涉及文件：

- `main.py`
- `agent/workflow.py`

`main.py` 先要求用户输入登录 ID，再创建一个新会话并循环读取需求：

```python
user_id = validate_user_id(input("请输入用户 ID 登录："))
workflow = TravelWorkflow(user_id=user_id)
response = workflow.run(user_input)
```

入口层不判断意图、不直接调用天气或预算工具，也不管理 JSON 文件。

### 3.2 创建请求标识并恢复状态

涉及文件：

- `utils/ids.py`
- `memory/memory_manager.py`
- `schemas/agent_state.py`

Workflow 为每条输入生成新的 `request_id`：

```text
req_xxxxxxxxxxxx
```

随后从：

```text
memory_data/sessions/<session_id>.json
```

加载当前会话，并从：

```text
memory_data/users/<user_id>.json
```

关联用户画像。

用户 ID 由用户每次启动时输入并持久化；每次启动生成新的 `session_id`，每条输入生成新的 `request_id`。ID 会经过格式校验，不能被用来访问任意文件路径。

### 3.3 分层更新长期画像与当前旅行

涉及文件：

- `tools/profile_tool.py`
- `prompts/profile_prompt.py`
- `schemas/user_profile.py`
- `services/llm_service.py`

执行策略：

```text
LLM 输出分层更新 JSON
  ├─ profile_updates → UserProfile（长期偏好）
  ├─ trip_updates → TravelRequest（本次目的地、日期、预算）
  └─ 异常 → 正则与关键词分层提取
```

更新器结合已有画像、当前旅行和最近六条消息，并支持：

- 普通字段设置与列表去重合并；
- 删除列表中的指定偏好；
- 用户明确要求时清空字段；
- 只说省份时记录省级目的地，不虚构城市。

### 3.4 生成带置信度的多步骤计划

涉及文件：

- `agent/router.py`
- `prompts/router_prompt.py`
- `schemas/route.py`

路由器先要求 LLM 返回 JSON：

```json
{
  "steps": [
    {"intent": "plan", "tool_name": "plan_itinerary", "confidence": 0.93},
    {"intent": "budget", "tool_name": "estimate_budget", "confidence": 0.89,
     "depends_on": ["plan_itinerary"]}
  ],
  "confidence": 0.89,
  "missing_fields": [],
  "needs_clarification": false
}
```

如果模型调用失败、JSON 无法解析或工具名不受支持，则使用关键词规则。

当前支持的工具：

| 工具名 | 用途 | Agent 阶段 |
|---|---|---|
| `recommend_destination` | 目的地推荐 | `recommending_destination` |
| `plan_itinerary` | 新建行程 | `planning_itinerary` |
| `refine_itinerary` | 修改已有行程 | `refining_itinerary` |
| `estimate_budget` | 预算估算 | `estimating_budget` |
| `check_weather` | 天气查询 | `checking_weather` |
| `convert_currency` | 汇率换算 | `converting_currency` |
| `finalize_plan` | 汇总导出 | `finalizing_plan` |

低于阈值、模型主动标记不明确，或请求修改不存在的行程时，Workflow 会先向用户追问；否则 Executor 按顺序执行所有步骤，并在每步后更新状态。

### 3.5 从注册表获取工具实例

涉及文件：

- `agent/executor.py`
- `tools/base.py`
- `tools/registry.py`
- `schemas/tool.py`

注册表保存：

```text
工具名称 → BaseTool 子类实例
```

例如：

```text
"check_weather" → WeatherTool()
```

执行器执行：

```python
tool = self.registry.get(route.tool_name)
result = tool.run(tool_input)
```

这里返回的是工具对象，不是普通函数；真正执行的是对象上的 `run()` 方法。

### 3.6 工具执行业务逻辑

所有具体工具继承 `BaseTool`，必须实现：

```python
def run(self, tool_input: dict[str, Any]) -> ToolResult:
    ...
```

`@abstractmethod` 保证没有实现 `run()` 的子类不能实例化。

工具成功时：

```python
ToolResult.ok(tool_name, data, metadata)
```

工具失败时：

```python
ToolResult.failure(tool_name, code, message)
```

这使 Workflow 不必针对每个工具设计一套异常返回结构。

### 3.7 更新状态、生成回复并保存

涉及文件：

- `agent/workflow.py`
- `agent/response_generator.py`
- `services/export_service.py`
- `memory/memory_manager.py`

成功结果根据工具类型写入：

```text
行程工具  → state.current_itinerary
预算工具  → state.budget_plan
天气工具  → state.weather_info
汇率工具  → state.exchange_info
```

`ResponseGenerator` 当前不再调用 LLM，只进行简单转换：

- 工具返回字符串：直接作为回复；
- 工具返回非字符串：使用 `str()`；
- 工具失败：输出错误消息。

每轮会分别保存原始回答、不可变完整快照和当前最新版本：

```text
outputs/users/<user_id>/sessions/<session_id>/requests/<request_id>.md
outputs/users/<user_id>/sessions/<session_id>/versions/v0001.md
outputs/users/<user_id>/sessions/<session_id>/latest.md
```

会话状态、长期画像和当前 `TripState` 随后写回本地 JSON。

## 4. 天气查询专项流程

天气功能体现了“LLM 理解 + 规则降级 + 真实 API”的组合设计。

涉及文件：

- `tools/weather_tool.py`
- `prompts/weather_prompt.py`
- `services/weather_service.py`
- `schemas/weather.py`
- `tests/unit/test_weather_tool.py`

```text
用户：魔都这周要不要带伞
  ↓
LLMService.generate_json()
  ↓
{"location": "上海", "days": 7}
  ↓
WeatherService.get_forecast("上海", 7)
  ↓
Open-Meteo 地理编码 + 天气预报 API
  ↓
WeatherResult
  ↓
Markdown 天气表格
```

如果 LLM 调用失败或输出类型无效：

```text
_extract_location() 正则提取地点
_extract_days()     正则/关键词提取天数
```

如果本轮没有地点，则尝试：

```python
state.user_profile.destination
```

结果元信息记录：

```json
{
  "source": "Open-Meteo",
  "parameter_extraction": "llm"
}
```

或者：

```json
{
  "source": "Open-Meteo",
  "parameter_extraction": "rules"
}
```

设计价值：即使模型不可用，常见天气表达仍然可以工作；即使模型理解成功，实时天气也不会由模型编造。

## 5. 目录和文件职责

### 5.1 入口与编排层 `agent/`

| 文件 | 职责 | 当前状态 |
|---|---|---|
| `main.py` | CLI 输入输出 | 已接入 |
| `agent/workflow.py` | 请求生命周期编排 | 已接入 |
| `agent/router.py` | LLM/规则路由 | 已接入 |
| `agent/executor.py` | 获取并执行工具 | 已接入 |
| `agent/response_generator.py` | ToolResult 转文本 | 已接入 |
| `agent/request_validator.py` | 兼容重导出 | 主流程未调用 |

### 5.2 工具层 `tools/`

| 文件 | 职责 | 数据来源 |
|---|---|---|
| `base.py` | 抽象工具接口 | 无 |
| `registry.py` | 注册和查找工具实例 | 无 |
| `profile_tool.py` | 提取用户画像 | LLM + 规则 |
| `destination_tool.py` | 推荐目的地 | LLM |
| `itinerary_plan_tool.py` | 生成新行程 | LLM |
| `itinerary_refine_tool.py` | 修改现有行程 | LLM |
| `budget_tool.py` | 估算预算 | LLM |
| `weather_tool.py` | 提参和格式化天气 | LLM + 规则 + API |
| `exchange_tool.py` | 提取金额币种、格式化汇率 | 规则 + API |
| `export_tool.py` | 汇总并导出方案 | 当前状态 |
| `travel_tools.py` | 旧导入路径兼容 | 不含业务实现 |

### 5.3 服务层 `services/`

| 文件 | 职责 | 边界 |
|---|---|---|
| `llm_service.py` | DeepSeek 文本/JSON调用 | LLM API |
| `weather_service.py` | 地理编码和天气预报 | Open-Meteo |
| `exchange_service.py` | 实时汇率换算 | Frankfurter |
| `export_service.py` | Markdown 构建与写入 | 文件系统 |
| `geocoding_service.py` | WeatherService 兼容重导出 | 当前无独立实现 |

项目已删除重复的 `utils/llm_client.py`，LLM 调用统一经过 `LLMService`。

### 5.4 Prompt 层 `prompts/`

| 文件 | 对应任务 |
|---|---|
| `profile_prompt.py` | 用户画像 JSON 提取 |
| `router_prompt.py` | 意图和工具 JSON 路由 |
| `weather_prompt.py` | 地点和天数 JSON 提取 |
| `destination_prompt.py` | 目的地推荐 Markdown |
| `itinerary_prompt.py` | 新行程 Markdown |
| `refine_prompt.py` | 行程修改 Markdown |
| `budget_prompt.py` | 预算 Markdown |
| `response_prompt.py` | 回复整理预留，尚未接入 |

### 5.5 Schema 层 `schemas/`

| 模型 | 表达的数据 |
|---|---|
| `UserProfile` | 跨轮次长期偏好 |
| `TravelRequest` | 一次旅行的需求 |
| `AgentState` | 当前会话执行状态 |
| `TripState` | 独立旅行项目及版本记录 |
| `RouteResult` | 路由意图、工具和缺失字段 |
| `ToolResult` / `ToolError` | 统一工具执行结果 |
| `Itinerary` | 结构化行程 |
| `BudgetPlan` | 结构化预算 |
| `WeatherResult` | 结构化天气 |
| `ExchangeResult` | 结构化汇率 |

当前实际差距：行程和预算工具仍返回 Markdown 字符串，没有生成 `Itinerary`、`BudgetPlan` 对象，因此对应 Validator 尚未形成自动校验闭环。

### 5.6 Memory、Validator、Exception、Utils

| 目录 | 职责 | 当前说明 |
|---|---|---|
| `memory/` | JSON 持久化、原子写入、损坏备份 | 用户、会话和 Trip 已接入 |
| `validators/` | 确定性业务校验 | 类已定义，主流程多数未调用 |
| `exceptions/` | 项目异常层级 | `LLMServiceError` 已使用，其余多为预留 |
| `utils/` | ID、日志、日期、重试、文件等通用能力 | `retry` 尚未接入外部调用 |

## 6. 数据模型关系

```text
UserProfile
  └─ 长期偏好，存在 AgentState.user_profile

TravelRequest
  └─ 当前旅行需求，存在 AgentState.travel_request

AgentState
  ├─ user_id / session_id / request_id
  ├─ current_stage
  ├─ current_itinerary
  ├─ budget_plan
  ├─ weather_info / exchange_info
  └─ chat_history[ChatMessage]

TripState（已同步持久化）
  ├─ TravelRequest
  ├─ current_itinerary
  ├─ budget_plan
  └─ itinerary_versions[ItineraryVersion]

RouteResult
  ├─ intent
  ├─ tool_name
  ├─ confidence（0-1，已赋值）
  └─ missing_fields

RoutePlan
  ├─ steps[RouteResult]
  ├─ confidence
  └─ needs_clarification / clarification_question
  └─ requires_existing_itinerary

ToolResult
  ├─ success
  ├─ data
  ├─ metadata
  └─ error[ToolError]
```

## 7. 项目涉及的核心理论

### 7.1 分层架构与关注点分离

分层架构把容易变化的部分隔离：

- Prompt 变化不应影响存储代码；
- 天气 API 变化不应影响 Workflow；
- CLI 更换为 FastAPI 时不应重写工具；
- 工具新增时不应扩展入口层 `if/elif`。

对应理论：Separation of Concerns、Single Responsibility Principle。

### 7.2 依赖倒置与依赖注入

工具构造函数允许注入服务：

```python
WeatherTool(weather_service=fake_weather, llm_service=fake_llm)
```

生产环境使用真实服务，测试环境使用 Fake。这样测试不需要访问网络，也不会产生模型费用。

对应理论：Dependency Injection、Dependency Inversion Principle、Test Double。

### 7.3 注册表模式

`ToolRegistry` 用映射代替长 `if/elif`：

```text
name → tool instance
```

新增工具只需实现接口并注册，Executor 无需了解具体类型。

对应理论：Registry Pattern、Open/Closed Principle、Polymorphism。

### 7.4 抽象基类和多态

`BaseTool` 通过 `ABC` 和 `@abstractmethod` 规定所有工具必须实现 `run()`。Executor 面向 `BaseTool` 编程，而不是面向 `WeatherTool`、`BudgetTool` 等具体类编程。

对应理论：Interface Contract、Polymorphism、Liskov Substitution Principle。

### 7.5 Schema-first 与 DTO

Pydantic 模型把松散字典转换为有字段、有类型、有默认值的数据对象，并提供：

- 校验；
- `model_dump()` 字典序列化；
- `model_dump_json()` JSON 序列化；
- 环境配置解析；
- 可读的类型提示。

对应理论：Schema-first Design、DTO、Runtime Validation。

### 7.6 状态机思想

`AgentStage` 将一次会话表示为不同阶段：收集偏好、推荐、规划、修改、预算、天气、汇率和导出。当前是轻量状态机，尚未实现严格的状态转移规则。

对应理论：Finite State Machine、Stateful Agent。

### 7.7 LLM Tool Use

当前系统将 LLM 用于两类任务：

1. **理解类**：画像提取、路由、天气参数提取；
2. **生成类**：目的地、行程、预算和行程修改。

理解类尽量返回 JSON，生成类当前返回 Markdown。真实数据查询交给确定性工具。

对应理论：Function Calling 思想、Tool-augmented LLM、Structured Output。

### 7.8 Prompt Engineering

项目使用的基本方法：

- System Prompt 约束角色与格式；
- 明确字段名和类型；
- 未知值使用 `null` 或 `[]`；
- 低温度提高结构化输出稳定性；
- 将 Prompt 从业务代码中分离。

当前没有使用 API 原生 JSON Schema/Structured Outputs，仍依赖提示词和解析器。

### 7.9 降级与容错

```text
LLM 成功 → 使用模型结果
LLM 失败 → 使用规则
外部 API 失败 → 返回 unavailable/ToolError
JSON 损坏 → 备份 .corrupt 并恢复默认模型
```

对应理论：Graceful Degradation、Fallback、Fault Tolerance。

### 7.10 原子写入

MemoryManager 先写临时文件，再使用 `replace()` 替换目标文件，降低程序中断时产生半个 JSON 文件的概率。

对应理论：Atomic File Replacement、Crash Consistency。

### 7.11 可观测性

每轮请求生成 `request_id`，日志记录工具、成功状态和耗时。未来可以扩展为结构化日志、trace/span 和指标。

对应理论：Logging、Tracing、Correlation ID、Observability。

### 7.12 测试金字塔与模型评测

传统代码适合确定性断言；LLM 输出需要同时使用：

- 字段精确匹配；
- 列表包含关系；
- 空值检查，防止编造；
- 人工 Rubric；
- 未来的重复运行稳定性和语义评分。

对应理论：Unit Test、Integration Test、Regression Test、Golden Dataset、LLM Evaluation。

## 8. 模型评测设计

相关文件：

- `tests/model_eval_cases.json`
- `tests/run_model_evals.py`
- `tests/MODEL_EVAL_GUIDE.md`

31条样例分为：

| 类别 | 数量 | 评分方式 |
|---|---:|---|
| 路由 | 9 | 自动字段匹配 |
| 用户画像 | 9 | 精确值、列表包含、空值检查 |
| 天气参数 | 7 | 自动字段匹配 |
| 开放式生成 | 6 | 人工 Rubric |

评测集重点暴露：

- 多意图单路由问题；
- 字段遗漏；
- 无依据补全；
- 中文金额和日期理解；
- 城市别称；
- 提示注入；
- 行程可执行性；
- 预算数学一致性；
- 幻觉控制。

当前自动评分是确定性匹配，`北京` 和 `北京市` 可能被判为不一致。下一阶段需要加入规范化和同义词映射，但应避免完全依赖另一个 LLM 当裁判。

## 9. 当前已知问题及改进优先级

### P0：影响正确性

1. **行程和预算缺少结构化校验闭环。** Schema 与 Validator 已存在，但工具只输出 Markdown。
2. **用户 ID 还是本地身份原型。** 尚无密码、令牌、权限控制和跨设备账户系统。

### P1：影响体验、成本和可观测性

1. 每轮请求可能依次调用画像 LLM、路由 LLM和工具 LLM；天气请求最多也会进行画像、路由、参数提取三次模型调用，存在延迟和成本优化空间。
2. 模型自报的 `confidence` 尚未通过离线数据校准，当前阈值主要用于工程分流。
3. 多处 `except Exception` 静默回退，日志无法区分模型失败和规则成功。
4. `MAX_RETRIES` 和 `utils/retry.py` 尚未接入外部调用。

### P2：工程完善

1. `TripState.itinerary_versions` 尚未记录结构化的行程差异，当前版本历史主要由 Markdown 快照承担。
2. 自定义异常除 LLM 外多数未实际使用。
3. `response_prompt.py` 尚未接入回复生成器。
4. `geocoding_service.py`、repository 模块和 `travel_tools.py` 主要是兼容层，可在确认无外部依赖后逐步清理。
5. 仍缺少完整的 API Mock、工作流集成测试和覆盖率报告。
6. 尚无 CI、格式化门禁和类型检查门禁。

## 10. 版本演进记录

### 原型阶段（2026-08-01 之前）

主要特点：

- 入口、路由、工具和状态逻辑集中；
- 依赖简单函数和长 `if/elif`；
- 工具职责和外部 API 边界不清晰；
- 难以测试和扩展。

学习价值：先完成端到端功能，再识别代码膨胀和耦合问题。

### Phase 1：基础工程重构（2026-08-01）

完成内容：

- 拆分 Agent、Tool、Service、Prompt、Schema、Validator、Memory；
- 引入 Workflow、Router、Executor、Registry；
- 引入统一 ToolResult；
- 引入用户/会话/Trip 数据模型；
- 引入本地持久化、日志、配置和异常结构；
- 保留旧导入兼容层。

学习价值：从“能运行的脚本”升级为“有边界的工程”。

### Phase 1.2：统一、容错和评测（2026-08-10）

完成内容：

- LLM 调用统一到 `LLMService`；
- 默认模型统一为 `deepseek-v4-flash`；
- 天气参数改为 LLM 优先、正则兜底；
- 为项目函数补全中文 docstring；
- 新增天气单元测试；
- 新增31条模型评测样例和评测脚本；
- README、CHANGELOG 和本指南同步更新。

学习价值：不仅实现功能，还开始关注降级、可测性、质量标准和版本文档。

### Phase 1.3：身份、分层记忆与多任务计划（2026-08-16）

完成内容：

- 用户输入 ID 登录，本地保存用户、会话和旅行状态；
- 分离 `UserProfile` 与 `TravelRequest`，加入删除和清空语义；
- 路由升级为带置信度、缺失字段和澄清机制的 `RoutePlan`；
- Executor 顺序执行多个工具并传递前置结果；
- 输出升级为 request 文件、不可变版本和 latest 聚合快照；
- 新增身份、画像、路由和版本管理单元测试。

学习价值：用原生 Python 掌握了 LangGraph 等框架底层仍需解决的 State、Plan、Execution、Checkpoint 和 Human-in-the-loop 问题。

### 下一阶段建议：Phase 2 结构化闭环

目标顺序：

1. 让行程和预算模型输出 JSON，再构造 `Itinerary`、`BudgetPlan`；
2. Validator 失败时执行一次修复提示或返回澄清问题；
3. 用评测集校准路由置信度和澄清阈值；
4. 为 `TripState.itinerary_versions` 增加结构化变更记录；
5. 扩展单元、集成和回归测试；
6. 添加 Ruff、mypy、pytest 和覆盖率 CI。

### 更后阶段：Phase 3 应用化

可选方向：

- FastAPI 服务；
- Streamlit 或 Web 前端；
- 数据库和用户登录；
- RAG 增强目的地知识；
- LangGraph 或自研状态图；
- 多 Agent 协作；
- 部署、监控、缓存和限流。

原则：只有当当前简单架构无法满足明确需求时，才引入更重的框架。

## 11. 学习路线：从读懂项目到达到应聘要求

### 阶段 A：Python 基础

需要能解释并手写：

- 类、实例、继承和多态；
- `ABC`、`@abstractmethod`、`@classmethod`、`@property`；
- `getattr()`、`setattr()`、`hasattr()`；
- 列表/字典推导式和 `**kwargs`；
- `SimpleNamespace`；
- 类型注解、`None`、联合类型；
- 异常处理和上下文管理器；
- UUID、Pathlib、JSON、正则表达式。

对应本项目文件：`tools/base.py`、`schemas/user_profile.py`、`utils/ids.py`、`memory/memory_manager.py`、`tools/weather_tool.py`。

### 阶段 B：Python 工程化

需要掌握：

- 包和模块导入；
- 配置与环境变量；
- 日志与异常层级；
- 单元测试、Fake、Mock；
- 依赖注入；
- 分层架构和设计模式；
- 原子写入与数据持久化；
- Git 和 CHANGELOG。

对应本项目文件：`config/`、`exceptions/`、`services/`、`tests/`、`memory/`。

### 阶段 C：LLM 应用开发

需要掌握：

- System/User Message；
- Temperature；
- JSON 结构化输出；
- Tool Use；
- Prompt Injection 基础防护；
- 幻觉与事实来源；
- fallback 和重试；
- token、延迟、费用；
- Eval Dataset 和回归评测。

对应本项目文件：`services/llm_service.py`、`prompts/`、`agent/router.py`、`tests/model_eval_cases.json`。

### 阶段 D：达到面试可讲水平

你应该能在不看代码的情况下回答：

1. 为什么把 Workflow、Router、Executor、Tool、Service 分开？
2. 为什么 Registry 比 `if/elif` 更适合扩展工具？
3. 为什么天气不应该让 LLM 直接生成？
4. 为什么天气参数使用 LLM 优先、正则兜底？
5. 为什么测试中要注入 Fake Service？
6. Pydantic 相比普通字典解决了什么问题？
7. 用户画像、会话状态和 TripState 有什么区别？
8. 当前系统如何处理 LLM 故障、API 故障和 JSON 损坏？
9. 当前架构最大的三个技术债是什么？
10. 如果支持“规划行程并查天气和预算”，你会如何设计多工具流程？
11. 如何评价一个 LLM Agent，而不仅是展示几个成功例子？
12. 为什么当前阶段没有直接使用 LangChain/LangGraph？

### 阶段 E：简历表达建议

在功能确实完成并有评测结果后，可以如实表达：

> 使用 Python、Pydantic 和 DeepSeek 构建旅行规划 Agent，设计 Workflow–Router–Executor–Tool 分层架构及工具注册表；封装天气、汇率外部 API，建立 LLM 优先/规则兜底的容错链路；实现本地状态持久化、统一结果模型和模型评测数据集。

避免在尚未实现时声称：

- 已实现 Multi-Agent；
- 已使用 RAG；
- 已完成生产级部署；
- 支持高并发；
- 评测达到某准确率但没有实际运行报告。

## 12. 常用开发和验证命令

指定项目环境：

```powershell
D:\Anoconda\envs\agent_env\python.exe
```

运行程序：

```powershell
D:\Anoconda\envs\agent_env\python.exe main.py
```

运行单元测试：

```powershell
D:\Anoconda\envs\agent_env\python.exe -m pytest -q
```

语法检查：

```powershell
D:\Anoconda\envs\agent_env\python.exe -m compileall -q .
```

运行少量模型评测：

```powershell
D:\Anoconda\envs\agent_env\python.exe tests\run_model_evals.py --limit 3
```

模型评测会访问 DeepSeek 并产生 API 用量，默认报告写入：

```text
outputs/model_eval_report.json
```

## 13. 新增工具的标准流程

1. 明确工具输入、输出和失败条件；
2. 在 `schemas/` 定义结构化数据；
3. 如需 LLM，在 `prompts/` 定义提示词；
4. 如需外部资源，在 `services/` 封装 API；
5. 在 `tools/` 创建 `BaseTool` 子类；
6. 在 `run()` 中返回 `ToolResult`；
7. 在 `tools/registry.py` 注册；
8. 在 Router Prompt 和规则路由中增加工具；
9. 在 Workflow 中决定成功结果写入哪个状态字段；
10. 添加成功、缺参、外部失败和 fallback 测试；
11. 增加模型评测样例；
12. 更新 README、CHANGELOG 和本文档。

## 14. 如何维护本项目档案

每次迭代至少更新三处：

### README

只记录当前用户需要知道的内容：功能、安装、运行、目录和验证命令。

### CHANGELOG

记录“本次改变了什么”，按日期或版本倒序添加，不覆盖历史。

推荐模板：

```markdown
## YYYY-MM-DD

### Added
- 新增能力

### Changed
- 行为或架构变化

### Fixed
- 修复的问题

### Tests
- 新增测试和结果

### Known limitations
- 仍未解决的问题
```

### PROJECT_GUIDE

记录“为什么这样设计”和“当前真实边界”。架构、流程、理论、技术债或学习路线变化时更新。

## 15. 最终学习目标检查表

- [ ] 能独立画出请求执行流程；
- [ ] 能解释每个目录的边界；
- [ ] 能新增一个工具并注册；
- [ ] 能为外部 API 编写 Fake 单元测试；
- [ ] 能定位一次模型 JSON 解析失败；
- [ ] 能解释规则 fallback 的价值和局限；
- [ ] 能把 Markdown 生成改成 Pydantic 结构化生成；
- [ ] 能设计多工具任务计划；
- [ ] 能运行并分析模型评测报告；
- [ ] 能清晰说明项目的技术债和下一阶段方案；
- [ ] 能用 STAR 方法讲述一次架构重构或质量改进；
- [ ] 能保证简历描述与实际代码和评测结果一致。

完成以上内容后，这个项目不再只是“调用大模型的 Demo”，而会成为一个能够展示 Python 工程能力、LLM 应用设计能力、测试思维和持续迭代能力的完整作品。
