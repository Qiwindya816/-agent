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

可选的高德 MCP 使用 Streamable HTTP。先确认服务端实际暴露的工具名，再配置显式白名单映射：

```env
MCP_ENABLED=true
AMAP_MCP_URL=https://your-mcp-server.example/mcp
AMAP_MCP_TOKEN=
AMAP_MCP_TOOL_MAP={"search_poi":"服务端POI工具名","geocode":"服务端地理编码工具名","plan_route":"服务端路线工具名"}
MCP_TIMEOUT_SECONDS=30
MCP_SSE_READ_TIMEOUT_SECONDS=300
```

`search_poi`、`geocode`、`plan_route` 是 TravelMind 内部稳定别名；映射值必须以目标 MCP Server 的 `tools/list` 结果为准。未设置 `MCP_ENABLED=true` 时不会建立 MCP 连接。

配置 URL 后可先执行工具发现（该命令不会打印 Token）：

```powershell
.\.venv\Scripts\python.exe -m scripts.check_mcp
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

阶段 9 的本地评测（不会修改业务数据）：

```powershell
# 纯关键词/模板召回基线
.\.venv\Scripts\python.exe -m scripts.manage_evals --no-embedding

# 包含 DashScope 向量召回的完整基线
.\.venv\Scripts\python.exe -m scripts.manage_evals
```

报告输出到 `outputs/evaluations/`，黄金集格式和指标口径见
[evaluation/README.md](evaluation/README.md)。RAG 黄金集在人工复核并标记为
`approved` 前只作为试运行基线，不应作为上线结论。

在线模型评测会产生 API 用量：

```powershell
.\.venv\Scripts\python.exe tests/run_model_evals.py --limit 3
```

## Docker Compose 部署

复制生产配置模板并填写自己的密钥，随后启动 PostgreSQL、Redis、FastAPI 和 Nginx 前端：

```powershell
Copy-Item .env.production.example .env
docker compose up --build -d
docker compose ps
```

默认页面地址为 `http://localhost:8080`。`.env.production.example` 只包含占位值；真实 Secret 只能保存在未提交的 `.env` 或部署平台的 Secret 管理中。小红书 MCP 依赖浏览器登录态，默认不进入生产 Compose，需要在授权且合规的独立运行环境中接入。

运行日志以 JSON Lines 写入 `logs/runtime.jsonl`，包含 request/session/trip ID、请求延迟以及模型 Token 用量，不记录 Prompt、模型正文或明文密钥。

## 当前边界

已经完成：

- 五节点 LangGraph 工作流和条件分支。
- 多步骤工具计划、依赖检查和统一 `ToolResult`。
- 用户、会话和旅行 ID，以及本地 JSON 状态。
- 长期画像与本次旅行约束分离。
- 目的地、行程、预算、天气、汇率和导出工具。
- Pydantic `Itinerary` 结构化生成、状态保存和确定性 Markdown 渲染。
- 可配置的 MCP Streamable HTTP 客户端、远端工具白名单和统一错误结果。
- LLM 失败时的部分规则回退。

正在重构：

- POI/路线 MCP 结果回填到结构化行程及确定性路线校验。
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
