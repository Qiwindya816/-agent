# TravelMind

TravelMind 是一个基于 Python、Pydantic 和 DeepSeek 的智能旅行规划 Agent。当前阶段是 **Phase 1.3 原生工作流增强**：暂不引入 LangChain、LangGraph 或 RAG，使用原生 Python 完成身份、记忆、多任务规划和结果版本管理。

当前默认模型为 `deepseek-v4-flash`。完整架构、执行流程、理论知识、版本演进和面试学习路线请阅读 [PROJECT_GUIDE.md](Document%20for%20study/PROJECT_GUIDE.md)。

当前版本保留命令行交互，并支持：

- 用户 ID 登录、会话隔离与本地记忆
- 长期用户画像与当前旅行需求分层更新
- 带置信度和澄清机制的多任务规划
- 目的地推荐
- 行程规划
- 行程修改
- 预算估算
- 天气查询
- 汇率换算
- Markdown 单轮回答、完整快照和历史版本保存
- LLM 结构化能力评测与人工质量检查

## Phase 1.x 架构目标

当前工程边界按以下职责划分：

```text
Workflow    负责编排完整请求流程
Router      负责判断用户意图和目标工具
Executor    负责从工具注册表中执行工具
Tool        负责具体业务能力
Service     负责 LLM、API、文件导出等外部资源
Prompt      负责集中管理提示词
Schema      负责数据约束
Validator   负责确定性校验
Repository  负责数据保存与读取
```

一次请求的主流程：

```text
用户 ID 登录并创建会话
  -> 用户输入
  -> 长期画像与当前旅行需求分别更新
  -> 带置信度的多步骤任务规划
  -> 按依赖顺序执行一个或多个工具
  -> ToolResult 统一结果
  -> 状态更新
  -> 自然语言响应
  -> 单轮回答与完整方案版本化保存
  -> 用户、会话和 TripState 持久化
```

## 当前目录结构

```text
TravelMind/
├── main.py
├── requirements.txt
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── PROJECT_GUIDE.md
├── .env.example
├── .gitignore
├── agent/
│   ├── __init__.py
│   ├── workflow.py
│   ├── router.py
│   ├── executor.py
│   ├── response_generator.py
│   └── request_validator.py
├── schemas/
│   ├── __init__.py
│   ├── user_profile.py
│   ├── travel_request.py
│   ├── agent_state.py
│   ├── trip_state.py
│   ├── itinerary.py
│   ├── budget.py
│   ├── weather.py
│   ├── exchange.py
│   ├── route.py
│   ├── tool.py
│   └── common.py
├── tools/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── profile_tool.py
│   ├── destination_tool.py
│   ├── itinerary_plan_tool.py
│   ├── itinerary_refine_tool.py
│   ├── budget_tool.py
│   ├── weather_tool.py
│   ├── exchange_tool.py
│   ├── export_tool.py
│   └── travel_tools.py
├── services/
│   ├── __init__.py
│   ├── llm_service.py
│   ├── weather_service.py
│   ├── exchange_service.py
│   ├── geocoding_service.py
│   └── export_service.py
├── prompts/
│   ├── __init__.py
│   ├── profile_prompt.py
│   ├── router_prompt.py
│   ├── destination_prompt.py
│   ├── itinerary_prompt.py
│   ├── refine_prompt.py
│   ├── budget_prompt.py
│   ├── weather_prompt.py
│   └── response_prompt.py
├── validators/
│   ├── __init__.py
│   ├── request_validator.py
│   ├── itinerary_validator.py
│   ├── budget_validator.py
│   └── state_validator.py
├── memory/
│   ├── __init__.py
│   ├── memory_manager.py
│   ├── profile_repository.py
│   ├── session_repository.py
│   └── trip_repository.py
├── exceptions/
│   ├── __init__.py
│   ├── base.py
│   ├── llm.py
│   ├── tool.py
│   ├── memory.py
│   ├── validation.py
│   └── external_api.py
├── config/
│   ├── __init__.py
│   └── settings.py
├── utils/
│   ├── __init__.py
│   ├── json_parser.py
│   ├── file_utils.py
│   ├── date_utils.py
│   ├── retry.py
│   ├── ids.py
│   ├── logger.py
│   └── change_logs.py
├── tests/
│   ├── model_eval_cases.json
│   ├── run_model_evals.py
│   ├── MODEL_EVAL_GUIDE.md
│   ├── unit/
│   │   └── test_weather_tool.py
│   ├── integration/
│   ├── fixtures/
│   └── regression/
├── data/
├── memory_data/
├── outputs/
└── logs/
```

## 关键文件职责

### 入口与工作流

- `main.py`：只负责命令行入口和输入循环，不再包含业务路由、工具调用、状态保存等逻辑。
- `agent/workflow.py`：核心编排器 `TravelWorkflow`。负责读取状态、更新用户画像、调用 Router、调用 Executor、更新状态、生成响应、保存结果。
- `agent/router.py`：多任务规划器。输出 `RoutePlan`、步骤置信度和澄清信息，失败时使用多关键词规则兜底。
- `agent/executor.py`：按依赖顺序执行 `RoutePlan` 中的多个工具，并让后续步骤读取前置结果。
- `agent/response_generator.py`：把一个或多个 `ToolResult` 合并为用户可读中文回复。

### 数据结构

- `schemas/user_profile.py`：跨旅行长期画像，支持设置、合并、删除列表项和显式清空。
- `schemas/travel_request.py`：本次旅行需求，与长期用户画像分离。
- `schemas/agent_state.py`：当前程序执行状态，包括 session、阶段、最近意图、最近工具、当前行程、预算、天气、汇率和聊天历史。
- `schemas/trip_state.py`：单次旅行任务状态，包含 trip ID、旅行需求、行程版本、预算和任务状态。
- `schemas/itinerary.py`：结构化行程 schema，包括活动、每日行程和完整行程。
- `schemas/budget.py`：预算计划 schema。
- `schemas/route.py`：单步骤 `RouteResult` 与多步骤 `RoutePlan`。
- `schemas/tool.py`：统一工具输出 `ToolResult` 和 `ToolError`。

### 工具体系

- `tools/base.py`：统一工具基类 `BaseTool`。
- `tools/registry.py`：工具注册表，统一注册和获取工具。
- `tools/profile_tool.py`：用户画像提取工具，LLM 失败时自动使用规则兜底。
- `tools/destination_tool.py`：目的地推荐工具。
- `tools/itinerary_plan_tool.py`：行程规划工具。
- `tools/itinerary_refine_tool.py`：行程修改工具。
- `tools/budget_tool.py`：预算估算工具。
- `tools/weather_tool.py`：天气查询工具。优先使用 LLM 提取地点和天数，LLM 异常或输出无效时使用正则规则兜底；真实天气仍由 Open-Meteo 提供。
- `tools/exchange_tool.py`：汇率换算工具。
- `tools/export_tool.py`：最终方案导出工具。
- `tools/travel_tools.py`：兼容旧导入路径的包装模块，新代码应优先使用独立工具模块。

### 服务层

- `services/llm_service.py`：统一 DeepSeek LLM 调用，提供文本输出和 JSON 输出接口。
- `services/weather_service.py`：调用 Open-Meteo 查询真实天气数据。
- `services/exchange_service.py`：调用 Frankfurter 查询真实汇率数据。
- `services/export_service.py`：生成并保存 Markdown 结果。
- `services/geocoding_service.py`：地理编码服务占位与兼容导出。

### Prompt 管理

所有主要 prompt 已从工具函数中迁移到 `prompts/`：

- `prompts/profile_prompt.py`
- `prompts/router_prompt.py`
- `prompts/destination_prompt.py`
- `prompts/itinerary_prompt.py`
- `prompts/refine_prompt.py`
- `prompts/budget_prompt.py`
- `prompts/weather_prompt.py`
- `prompts/response_prompt.py`

其中 `response_prompt.py` 当前只保留系统提示词，尚未接入 `ResponseGenerator`。

### 校验器

- `validators/request_validator.py`：检查正式规划行程所需字段。
- `validators/itinerary_validator.py`：检查结构化行程基本有效性。
- `validators/budget_validator.py`：检查预算项是否为负、是否超预算。
- `validators/state_validator.py`：检查状态是否满足某些工具执行前置条件。

### 记忆与存储

- `memory/memory_manager.py`：统一 JSON 读写，支持原子写入、损坏 JSON 备份、默认状态恢复。
- `memory/profile_repository.py`：用户画像仓储包装。
- `memory/session_repository.py`：会话状态仓储包装。
- `memory/trip_repository.py`：旅行任务仓储包装。

主工作流会同步保存用户画像、会话状态和当前 `TripState`。

运行时数据保存在：

```text
memory_data/users/<user_id>.json
memory_data/sessions/<session_id>.json
memory_data/trips/<trip_id>/trip.json
outputs/users/<user_id>/sessions/<session_id>/requests/<request_id>.md
outputs/users/<user_id>/sessions/<session_id>/versions/v0001.md
outputs/users/<user_id>/sessions/<session_id>/latest.md
```

这些文件不会提交到 Git。

### 配置、异常与工具函数

- `config/settings.py`：统一读取模型、API、路径、超时等配置。
- `exceptions/`：统一异常层级。
- `utils/json_parser.py`：清理和解析 LLM JSON。
- `utils/ids.py`：生成 request/session/trip ID。
- `utils/logger.py`：运行时日志。
- `utils/retry.py`：通用重试工具。
- `utils/change_logs.py`：文件变更追踪工具。

## 环境配置

安装依赖：

```bash
pip install -r requirements.txt
```

复制环境变量模板：

```bash
copy .env.example .env
```

在 `.env` 中填写：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_MODEL=deepseek-v4-flash
```

运行：

```bash
python main.py
```

启动后必须输入 3-64 位用户 ID（英文字母、数字、下划线或连字符）。该 ID 会写入用户档案；每次启动创建新的会话 ID，后续可作为正式登录服务的本地原型。

本项目已配置的 Conda 解释器为：

```text
D:\Anoconda\envs\agent_env\python.exe
```

## 验证命令

编译检查：

```bash
python -m compileall -q .
```

工具注册表冒烟测试：

```bash
python -c "from tools.registry import build_default_registry; print(build_default_registry().list_tools())"
```

用户画像规则兜底测试：

```bash
python -c "from tools.profile_tool import extract_user_profile; p=extract_user_profile('我预算8000人民币，喜欢美食和城市漫步', use_llm=False); print(p.model_dump_json(indent=2, exclude_none=True))"
```

Workflow 兜底测试：

```bash
python -c "from agent.workflow import TravelWorkflow; print(TravelWorkflow().run('第三天太累了，帮我安排得轻松一点。'))"
```

运行单元测试：

```bash
python -m pytest -q
```

先运行 3 条在线模型评测样例：

```bash
python tests/run_model_evals.py --limit 3
```

模型评测会实际调用 DeepSeek 并产生 API 用量。全部31条样例、评分规则和分析方法见 [tests/MODEL_EVAL_GUIDE.md](tests/MODEL_EVAL_GUIDE.md)。

## 新增工具开发流程

1. 在 `schemas/` 中创建工具输入或输出 schema。
2. 在 `prompts/` 中创建或更新工具 prompt。
3. 在 `tools/` 中创建独立工具文件。
4. 继承 `BaseTool`。
5. 实现 `run(tool_input)`。
6. 返回统一 `ToolResult`，失败时返回 `ToolError`。
7. 在 `tools/registry.py` 中注册工具。
8. 如需外部 API，放到 `services/`，不要直接写在工具中。
9. 添加 validator 或测试。
10. 更新 README 和 CHANGELOG。

## Phase 1 暂不实现

- Streamlit 前端
- FastAPI 接口
- LangChain
- LangGraph
- RAG
- Multi-Agent
- MCP
- 正式数据库
- 带密码、令牌和权限控制的正式用户登录系统
- 在线部署
- 历史会话选择与恢复界面
- 结构化行程和预算生成后的自动校验闭环
- 基于离线评测校准路由 confidence 阈值

当前架构会为这些能力预留接口，但不在第一阶段直接引入。
