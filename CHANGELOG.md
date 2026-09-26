# 更新日志

## 2026-08-16

### Phase 1.3 原生工作流增强

- CLI 启动时要求输入用户 ID，完成格式校验、用户档案持久化和每次启动的新会话创建。
- `UserProfile` 只承载长期偏好，新增并接入 `TravelRequest` 保存当前目的地、日期、天数和预算；支持显式清空与删除列表项。
- 画像提取 Prompt 开始结合已有画像、当前旅行和最近对话，并支持省级目的地而不虚构城市。
- 路由输出升级为带整体及步骤置信度的 `RoutePlan`，支持澄清追问和单轮多工具计划。
- `ToolExecutor` 支持按依赖顺序执行多个工具，并在每步后立即更新状态供后续工具使用。
- 结果保存改为 request 独立文件、不可变版本快照和 `latest.md` 聚合方案，避免历史结果被覆盖。
- 会话保存时同步持久化 `TripState`；生成型工具会读取长期画像、当前旅行和已有行程上下文。
- 新增身份、画像更新、省级目的地、多任务路由、执行顺序和导出版本测试。
- 修复 Router 未接收长期画像而重复询问偏好的问题；增加“有画像直接使用、无画像继续澄清”的回归测试，当前单元测试共 13 项。

## 2026-08-10

### Phase 1.2 工程统一与模型评测

- 将 LLM 调用统一到 `services/llm_service.py`，删除未被引用的旧实现 `utils/llm_client.py`。
- 将默认模型统一为 `deepseek-v4-flash`，同步更新 `config/settings.py`、`.env.example` 和 README。
- 为当前项目105个函数和方法补齐中文 docstring，并为核心工作流补充逐步说明。
- 明确保留 `tools/travel_tools.py`、repository 包装模块等兼容重导出；它们不包含重复业务实现。

### 天气参数提取升级

- 新增 `prompts/weather_prompt.py`，要求模型以严格 JSON 输出 `location` 和 `days`。
- `WeatherTool` 改为 LLM 优先提取天气参数，模型异常或输出无效时自动回退正则规则。
- 用户本轮未提供地点时，继续使用用户画像中的目的地。
- 天气结果元信息新增 `parameter_extraction`，用于区分 `llm` 和 `rules`。
- 天气数据仍由 Open-Meteo 提供，避免让模型生成实时天气事实。
- 使用 `SimpleNamespace` 简化旧式 `check_weather()` 兼容包装中的临时状态对象。

### 测试与模型评测

- 新增 `tests/unit/test_weather_tool.py`，覆盖 LLM 成功、LLM 失败后规则回退和画像地点回退。
- 当前单元测试结果：`3 passed`。
- 新增 `tests/model_eval_cases.json`，包含31条路由、用户画像、天气参数和开放式生成评测样例。
- 新增 `tests/run_model_evals.py`，可调用当前模型并生成组件通过率与失败明细。
- 新增 `tests/MODEL_EVAL_GUIDE.md`，说明自动评分、人工评分、API 用量和问题分析方法。

### 文档与已知限制

- 更新 README，使目录结构、天气提取策略、测试命令和实际持久化范围与当前代码一致。
- 新增 `PROJECT_GUIDE.md`，记录完整架构、执行链路、文件职责、理论知识、版本演进和面试学习路线。
- 当前仍只支持单工具路由；`confidence`、`missing_fields`、`TripState` 和结构化结果校验尚未接入主流程。

## 2026-08-01

### Phase 1 基础工程重构

- 删除与目标包结构冲突的根目录 `agent.py`，新增 `agent/` 包。
- 简化 `main.py`，使其只负责命令行入口和输入循环。
- 新增 `TravelWorkflow`，集中编排画像提取、路由、工具执行、状态更新和结果保存。
- 新增 `TravelRouter`，实现 LLM 路由与关键词规则 fallback。
- 新增 `ToolExecutor`，通过工具注册表执行工具，移除入口层的大段 `if/elif`。
- 新增 `ResponseGenerator`，统一把工具结果转换为用户回复。

### Schema 与工具体系

- 新增 `TravelRequest`、`TripState`、`RouteResult`、`ToolResult`、`ToolError`、`BudgetPlan`、`WeatherResult` 和 `ExchangeResult` 等 schema。
- 完善结构化行程 schema，包括 `Activity`、`DailyItinerary` 和 `Itinerary`。
- 新增 `BaseTool` 和 `ToolRegistry`。
- 将原旅行工具拆分为独立模块：
  - `destination_tool.py`
  - `itinerary_plan_tool.py`
  - `itinerary_refine_tool.py`
  - `budget_tool.py`
  - `weather_tool.py`
  - `exchange_tool.py`
  - `export_tool.py`
- 保留 `tools/travel_tools.py` 作为旧导入路径兼容包装。

### Service、Prompt、Memory

- 新增 `services/llm_service.py`，统一管理 DeepSeek 调用。
- 新增 `services/weather_service.py` 和 `services/exchange_service.py`，分别封装天气和汇率 API。
- 新增 `services/export_service.py`，统一保存 Markdown 输出。
- 将主要 prompt 迁移到 `prompts/`。
- 重构 `memory/memory_manager.py`，支持用户、session、trip 分离存储，增加原子写入和损坏 JSON 备份。
- 新增 `memory_data/` 运行时存储目录，并加入 `.gitignore`。

### 配置、异常、校验与测试骨架

- 新增 `config/settings.py` 和 `.env.example`。
- 新增统一异常目录 `exceptions/`。
- 新增请求、行程、预算和状态校验器。
- 新增 `utils/ids.py`、`utils/logger.py`、`utils/retry.py`、`utils/file_utils.py` 和 `utils/date_utils.py`。
- 新增 `pyproject.toml`。
- 新增 `tests/unit`、`tests/integration`、`tests/fixtures` 和 `tests/regression` 目录骨架。

### 验证

- 已通过全项目编译检查：

```bash
python -m compileall -q .
```

- 已验证工具注册表可加载默认工具。
- 已验证用户画像规则兜底可提取中文预算、币种和兴趣。
- 已验证 Workflow 在“没有现有行程却要求修改行程”的场景下返回友好错误，不会崩溃。
