# TravelMind

TravelMind 是一个正在重构中的智能旅行助手。当前唯一运行架构基于 LangGraph，由主协调、用户反馈、任务规划、工具执行和结果总结五类节点协作完成一轮请求。

## 当前架构

```text
用户输入
  → Coordinator Agent       恢复用户、会话和请求上下文
  → Feedback Agent          更新当前约束与长期偏好
  → Planner Agent           拆解任务并生成工具依赖计划
  → Tool Execution Agent    调用白名单工具并归一化结果
  → Summarizer Agent        合并结果、错误和澄清信息
```

Planner 判断信息不足时，会跳过工具执行并由 Summarizer 返回澄清问题。城市推荐、预算、天气、汇率和行程规划属于专业能力，通过统一工具注册表进入执行节点；复杂能力成熟后可以升级为 LangGraph 子图。

详细设计见 [MULTI_AGENT_ARCHITECTURE.md](Document%20for%20study/MULTI_AGENT_ARCHITECTURE.md)，项目学习指南见 [PROJECT_GUIDE.md](Document%20for%20study/PROJECT_GUIDE.md)。

## 目录结构

```text
TravelMind/
├── main.py                 # 唯一 CLI 入口
├── multi_agent/            # LangGraph 状态、节点、图与工作流
├── tools/                  # 可注册的业务工具
├── services/               # LLM 与外部 API 服务
├── schemas/                # Pydantic 数据契约
├── memory/                 # 当前本地状态仓储
├── prompts/                # 集中管理的提示词
├── validators/             # 确定性校验
├── config/                 # 环境配置
├── tests/                  # 单元测试与模型评测
└── Document for study/     # 当前架构和学习文档
```

旧的 `agent/` 编排包、旧 CLI、兼容转发模块和旧架构文档已删除。通用的工具、服务、Schema、校验器和仓储继续作为新架构的能力层使用。

## 本地运行

要求 Python 3.12。项目已使用本地 `.venv`：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中设置有效的 DeepSeek 配置：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
LLM_TEMPERATURE=0.3
API_TIMEOUT=10
MAX_RETRIES=1
```

启动：

```powershell
.\.venv\Scripts\python.exe main.py
```

用户 ID 允许英文字母、数字、下划线和连字符，长度为 3～64 位。每次启动默认创建新会话；工作流内部使用 `session_id` 作为 LangGraph `thread_id`。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q .
.\.venv\Scripts\python.exe -m pip check
```

在线模型评测会产生 API 用量：

```powershell
.\.venv\Scripts\python.exe tests/run_model_evals.py --limit 3
```

## 当前边界

已经完成：

- 五节点 LangGraph 工作流和条件分支。
- 多步骤工具计划、依赖检查和统一 `ToolResult`。
- 用户、会话和旅行 ID，以及本地 JSON 状态。
- 长期画像与本次旅行约束分离。
- 目的地、行程、预算、天气、汇率和导出工具。
- LLM 失败时的部分规则回退。

正在重构：

- 结构化 `TripPlan` 全链路。
- 持久化 LangGraph Checkpoint。
- MCP 地图、天气和铁路 Gateway。
- BM25、向量、地理和模板混合召回。
- 长期记忆证据与个性化排序。

未接入的能力不会在文档中标记为已完成，实时数据不可用时也不得由模型补写事实。

## 开发约束

- 节点间状态保存原始结构化数据，不保存拼接后的 Prompt。
- Planner 负责计划，Executor 负责执行，业务工具不直接控制工作流跳转。
- 所有外部工具必须有参数 Schema、统一结果、来源、时间和明确错误。
- 价格汇总、时间冲突、路线耗时和排序等确定性逻辑使用普通代码。
- API Key 仅写入本地 `.env`，不得提交仓库。
