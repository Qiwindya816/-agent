# TravelMind 后续建设总体计划

> 依据：`travel-agent-configuration-checklist.md`、当前项目实际实现状态，以及后续目标收敛结果。
> 目标：逐步完成多智能体协作与 MCP 工具调用、混合 RAG 与多路召回、长短期记忆与个性化推荐、三层数据隔离、上下文管理、后端与前端建设。
> 原则：先建立数据与隔离地基，再逐步接入工具、知识库、记忆、排序和应用层；所有实时事实必须来自外部工具，不允许模型编造。

---

## 当前已有能力

当前项目已经具备以下基础：

- 五节点 LangGraph 工作流：`Coordinator → Feedback → Planner → Tool Executor → Summarizer`
- 高德 MCP 已接入：
  - `search_poi → maps_text_search`
  - `geocode → maps_geo`
  - `plan_route → maps_direction_transit_integrated`
- 已实现 `geocode → plan_route` 自动坐标回填链路
- 已具备结构化 `Itinerary`
- 用户 / 会话 / 行程已有本地 JSON 存储
- 单元测试覆盖核心链路
- DeepSeek 模型服务已配置
- 天气与汇率工具已可调用真实外部 API

当前仍缺：

- PostgreSQL + pgvector 数据库
- 严格 `user_id / session_id / trip_id` 三层隔离
- LangGraph PostgreSQL Checkpoint
- 12306 / 铁路 MCP
- 统一 MCP Gateway
- 混合 RAG
- 长期 Memory
- 个性化排序
- FastAPI 后端
- Vue 3 前端
- 上下文压缩与恢复
- 可观测性和生产化体系

---

# 阶段 0：目标收敛与技术选型确认

## 0.1 技术栈选择

| 板块 | 选型 |
|---|---|
| 数据库 | PostgreSQL + pgvector |
| ORM / Migration | SQLAlchemy 2.x + Alembic |
| 后端 | FastAPI |
| 前端 | Vue 3 + TypeScript + Vite + Pinia |
| 多智能体 | LangGraph |
| 模型 | DeepSeek / Qwen |
| Embedding | DashScope `text-embedding-v3` |
| Reranker | 第二阶段按评测结果接入 |
| 地图 | 高德 |
| 铁路 | 12306 / 铁路 MCP |
| 缓存 / 限流 | Redis |
| 部署 | Docker Compose |

## 0.2 第一版优先接入的 MCP Provider

优先：

- 高德地图
- 12306 / 铁路

暂缓：

- 百度地图
- 航班数据
- 美团通用数据
- 自动订票和支付

---

# 阶段 1：数据库与三层隔离体系

## 1.1 目标

建立真正的数据库版本：

```text
user_id
  → session_id
      → trip_id
          → plan versions
```

必须保证：

1. 用户之间不能互相访问数据。
2. 同一个用户的不同会话不能互相污染。
3. 同一个会话里的不同 trip plan 也要隔离。
4. 所有查询必须带租户边界。
5. 删除用户时，其会话、行程、Memory、RAG 私有数据全部级联删除。

## 1.2 数据表设计

### 用户与会话

#### `users`

| 字段 | 说明 |
|---|---|
| `user_id` | 主键 |
| `display_name` | 显示名 |
| `personalization_enabled` | 是否启用个性化 |
| `long_term_memory_enabled` | 是否启用长期记忆 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

#### `chat_sessions`

| 字段 | 说明 |
|---|---|
| `session_id` | 主键 |
| `user_id` | 外键，强制隔离 |
| `title` | 会话标题 |
| `current_trip_id` | 当前活动行程 |
| `status` | active / archived |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

#### `chat_messages`

| 字段 | 说明 |
|---|---|
| `message_id` | 主键 |
| `session_id` | 外键 |
| `user_id` | 冗余外键，用于查询隔离 |
| `role` | user / assistant / tool |
| `content` | 文本 |
| `structured_payload` | JSONB |
| `token_count` | Token 数 |
| `created_at` | 创建时间 |

### 行程与版本

#### `trips`

| 字段 | 说明 |
|---|---|
| `trip_id` | 主键 |
| `user_id` | 外键 |
| `session_id` | 外键 |
| `destination` | 目的地 |
| `start_date` | 开始日期 |
| `end_date` | 结束日期 |
| `status` | planning / confirmed / archived |
| `current_version` | 当前版本号 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

#### `trip_plan_versions`

| 字段 | 说明 |
|---|---|
| `version_id` | 主键 |
| `trip_id` | 外键 |
| `user_id` | 冗余隔离字段 |
| `version_number` | 版本号 |
| `itinerary` | 结构化 JSONB |
| `change_reason` | 修改原因 |
| `source_agent` | 产生该版本的 Agent |
| `created_at` | 创建时间 |

#### `trip_feedback`

| 字段 | 说明 |
|---|---|
| `feedback_id` | 主键 |
| `trip_id` | 外键 |
| `user_id` | 外键 |
| `version_id` | 对应版本 |
| `activity_id` | 具体活动，可为空 |
| `feedback_type` | accept / reject / modify |
| `reason` | 用户原因 |
| `created_at` | 创建时间 |

### Memory 表

#### `memory_items`

核心字段：

```text
memory_id
user_id
memory_type
category
statement
structured_value
scope
polarity
importance
confidence
evidence_count
source_type
status
embedding
first_observed_at
last_observed_at
last_confirmed_at
expires_at
```

Memory 类型：

```text
explicit      用户明确要求记住
episodic      历史旅行行为
semantic      从多次行为归纳出的稳定偏好
scenario      特定旅行场景偏好
```

#### `memory_evidence`

```text
evidence_id
memory_id
user_id
session_id
message_id
trip_id
evidence_text
observed_at
```

#### `memory_relations`

```text
relation_id
source_memory_id
target_memory_id
relation_type
weight
```

### RAG 表

#### `rag_sources`

```text
source_id
source_type
name
url
license
authorization_status
owner_user_id
created_at
updated_at
```

`owner_user_id` 为空表示公共知识库，非空表示用户私有资料。

#### `rag_documents`

```text
document_id
source_id
owner_user_id
content_hash
raw_file_path
title
published_at
fetched_at
status
```

#### `rag_chunks`

```text
chunk_id
document_id
owner_user_id
chunk_text
chunk_type
city
district
poi_id
latitude
longitude
theme
travel_days
audience
season
price_level
embedding
tsv
created_at
```

#### `rag_ingestion_jobs`

```text
job_id
source_id
document_id
status
error_message
started_at
finished_at
```

### 工具调用与 Provider 健康

#### `tool_calls`

```text
tool_call_id
user_id
session_id
trip_id
provider
tool_name
arguments
result
status
error_code
latency_ms
retries
cache_hit
created_at
```

#### `provider_health`

```text
provider_name
status
success_rate
average_latency
last_success_at
last_failure_at
circuit_state
```

### LangGraph Checkpoint

#### `langgraph_checkpoints`

按 `thread_id` 保存，每个 `session_id` 对应一个 thread。

## 1.3 隔离策略

### 查询层强制隔离

所有 Repository 查询必须带：

```python
user_id = current_user_id
session_id = current_session_id
trip_id = current_trip_id
```

禁止只按全局 ID 查询。

### 数据库层兜底

建立组合索引：

```text
chat_sessions(user_id, session_id)
chat_messages(user_id, session_id, message_id)
trips(user_id, session_id, trip_id)
trip_plan_versions(user_id, trip_id, version_id)
memory_items(user_id, memory_id)
rag_chunks(owner_user_id, chunk_id)
```

后期启用 PostgreSQL Row Level Security，作为第二道防线。

## 1.4 阶段验收标准

- [ ] PostgreSQL + pgvector 安装完成
- [ ] Alembic migration 可创建全部核心表
- [ ] 用户 A 无法读取用户 B 的会话
- [ ] 同一用户会话 A 无法读取会话 B 的行程
- [ ] 同一 trip 的版本互不覆盖
- [ ] 删除用户后，其 Memory、RAG 私有数据、行程、会话全部删除
- [ ] 所有 Repository 层有隔离单元测试
- [ ] 当前 JSON 存储可以迁移到数据库

---

# 阶段 2：上下文管理与 LangGraph Checkpoint

## 2.1 目标

解决多轮对话、会话恢复、上下文过长、状态串扰的问题。

## 2.2 引入 PostgreSQL Checkpointer

将当前进程内 Checkpointer 替换为：

```text
LangGraph PostgreSQL Checkpoint
```

每个会话使用：

```text
thread_id = session_id
```

这样页面刷新、服务重启后，会话状态都可以恢复。

## 2.3 短期状态结构

短期上下文保存：

```text
当前目的地
当前出发地
旅行日期
旅行天数
同行人
预算
已确认约束
未解决问题
本次临时偏好
已拒绝候选
当前 TripPlan 版本
工具结果及过期时间
```

## 2.4 上下文优先级

构建统一 `ContextBuilder`，按优先级注入 Prompt：

```text
1. 用户本轮输入
2. 当前旅行硬约束
3. 当前结构化行程
4. 未解决问题
5. 最近 N 轮对话
6. 工具实时结果
7. 旧对话摘要
8. 长期 Memory
9. RAG 检索结果
```

原则：

- 当前明确要求优先
- 当前旅行上下文优先于长期偏好
- 明确偏好优先于推断偏好
- 最近确认内容优先于旧内容

## 2.5 上下文压缩

初始配置：

```text
最近保留轮数：8
生成摘要轮数：12
最大上下文 Token：6000
摘要最大 Token：800
```

摘要必须保留：

- 已确认约束
- 目的地
- 日期
- 预算
- 用户拒绝过的方案
- 当前行程版本
- 尚未回答的问题

## 2.6 工具结果时效管理

每个工具结果带：

```text
provider
source
fetched_at
expires_at
```

建议有效期：

| 数据 | 建议有效期 |
|---|---|
| 天气 | 1～3 小时 |
| POI 营业状态 | 1 天 |
| 路线耗时 | 30 分钟 |
| 车次 | 5～15 分钟 |
| 汇率 | 1 小时 |

过期后不能继续作为事实注入，必须重新查询或标注不确定。

## 2.7 阶段验收标准

- [ ] 服务重启后会话可以恢复
- [ ] 切换会话后不会串状态
- [ ] 超长对话可以生成结构化摘要
- [ ] 摘要不会丢失关键约束
- [ ] 新问题不会无条件清空当前 TripPlan
- [ ] 用户可以新建完全独立的旅行计划
- [ ] 上下文注入有 Token 预算控制
- [ ] 工具结果过期后会被标记或刷新

---

# 阶段 3：MCP Gateway 与实时服务统一接入

## 3.1 目标

把高德、天气、铁路等外部能力统一成稳定、可观测、可降级的工具层。

## 3.2 Provider 抽象

建立统一接口：

```python
class ToolProvider:
    name: str
    tools: list[ToolDescriptor]

    def health(self) -> ProviderHealth: ...

    def call(self, tool_name: str, arguments: dict) -> ToolResult: ...
```

每个工具必须定义：

```text
工具名
描述
输入 Schema
输出 Schema
超时时间
重试策略
缓存策略
降级策略
```

## 3.3 当前已具备

```text
高德 MCP
├─ search_poi
├─ geocode
└─ plan_route
```

已实现：

```text
geocode → plan_route 坐标回填
```

## 3.4 高德能力结构化

### POI 统一模型

```text
poi_id
name
city
district
address
latitude
longitude
category
rating
price_level
opening_hours
source
fetched_at
expires_at
```

### 路线统一模型

```text
route_id
origin
destination
transport_mode
distance
duration
walking_distance
segments
instructions
provider
fetched_at
expires_at
```

### 地理编码统一模型

```text
address
city
district
adcode
latitude
longitude
level
provider
```

## 3.5 天气工具统一

当前天气走 Open-Meteo，后续统一进 MCP Gateway：

```text
weather
├─ city
├─ date
├─ weather
├─ min_temperature
├─ max_temperature
├─ precipitation
├─ source
└─ fetched_at
```

即使 Provider 不是 MCP，也统一返回 `ToolResult`。

## 3.6 12306 / 铁路 MCP

新增工具：

```text
search_train_stations
search_train_tickets
search_train_schedule
```

输出统一为：

```text
train_number
departure_station
arrival_station
departure_time
arrival_time
duration
seat_classes
prices
availability
source
fetched_at
expires_at
```

约束：

- 车次和票价必须来自实时服务
- 服务失败时不能由 LLM 编造

## 3.7 工具治理能力

加入：

```text
超时控制
重试
限流
熔断
缓存
健康检查
调用日志
错误分类
```

统一错误类型：

```text
timeout
rate_limited
auth_failed
no_result
provider_error
invalid_params
```

## 3.8 工具结果回填行程

本阶段重点：

```text
POI → Itinerary Activity
Route → Activity Transport
Weather → Day Advisory
Train → Cross-city Transport
```

行程活动结构包含：

```text
activity_id
title
poi_id
latitude
longitude
start_time
end_time
duration
city
district
transport_to_next
source
status
```

## 3.9 阶段验收标准

- [ ] 所有外部工具返回统一 `ToolResult`
- [ ] 所有工具有输入输出 Schema
- [ ] 高德 POI / geocode / route / weather 全部可调用
- [ ] 12306 查询可调用
- [ ] 工具失败时不会编造实时数据
- [ ] 每次调用记录 latency、状态、错误、缓存命中
- [ ] POI 结果可以进入行程活动
- [ ] 路线结果可以绑定到活动之间的交通段
- [ ] 天气结果可以作为日程建议
- [ ] Provider 有健康状态和熔断策略

---

# 阶段 4：RAG 知识库建设

## 4.1 目标

构建官方旅游信息、用户授权攻略、多日游模板三类专业知识库，并实现多路召回、融合和引用。

## 4.2 知识类型

### A. Official Facts 官方事实

来源：

```text
景区官网
政府文旅平台
官方公众号
权威交通信息
```

内容：

```text
开放时间
门票
预约政策
闭馆日期
地址
交通指引
```

### B. Authorized Guides 授权攻略

来源：

```text
用户上传
作者授权内容
合作内容
```

必须记录授权状态。

### C. Templates 多日游模板

来源：

```text
人工整理
系统沉淀
高质量历史行程
```

结构：

```text
城市
天数
主题
人群
每日安排
预算档位
```

## 4.3 数据摄取流程

```text
上传 / 抓取
→ 授权校验
→ 原始文件存储
→ 内容解析
→ 去重
→ 结构化切块
→ 元数据标注
→ Embedding
→ 入库
```

必须支持：

```text
内容 hash 去重
来源登记
删除后同步删除向量
重新摄取
```

## 4.4 结构化切块

### 官方事实

按实体切：

```text
一个景点 / 一个博物馆 / 一个政策
```

### 攻略

按章节和段落切：

```text
标题
子标题
段落
列表
```

### 模板

按天切：

```text
Day 1
Day 2
Day 3
```

同时保留整体模板元数据。

## 4.5 元数据标注

每个 chunk 必须包含：

```text
city
district
poi_id
latitude
longitude
theme
travel_days
audience
season
budget_level
source_id
published_at
fetched_at
license
```

## 4.6 多路召回

### BM25

使用 PostgreSQL `tsvector`。

适合：

```text
景点名
地点
政策
关键词
```

### 向量召回

使用 pgvector。

适合：

```text
语义相似
自然语言需求
模糊描述
```

### 地理召回

根据用户行程城市或当前 POI 坐标，召回附近相关内容。

例如：

```text
故宫附近
2 公里内
北京东城区
```

### 模板召回

根据：

```text
城市
天数
人群
主题
预算
```

召回合适的多日游模板。

## 4.7 RRF 融合

初始配置：

```text
Dense Top-K: 20
BM25 Top-K: 20
Geo Top-K: 20
Template Top-K: 20
RRF Top-K: 15
```

## 4.8 Reranker

第一阶段先建立评测基线，不强制开启。

启用条件：

- [ ] 有最小 RAG 测试集
- [ ] 已测量无 Reranker 的 Recall / nDCG
- [ ] Reranker 能带来明显提升
- [ ] 成本和延迟可接受

最终配置：

```text
Rerank Top-K: 6
最终上下文数量: 4
```

## 4.9 引用展示

所有 RAG 生成内容必须展示：

```text
来源名称
来源链接
发布时间
抓取时间
授权状态
```

不允许无来源引用。

## 4.10 公共与私有数据隔离

规则：

```text
公共 RAG: owner_user_id IS NULL
用户 RAG: owner_user_id = current_user_id
```

检索过滤：

```sql
WHERE owner_user_id IS NULL
   OR owner_user_id = :current_user_id
```

## 4.11 阶段验收标准

- [ ] 建立官方事实、授权攻略、模板三类知识库
- [ ] 每个数据源有授权登记
- [ ] 原始文件保存在对象存储或本地受控目录
- [ ] 内容 hash 去重有效
- [ ] chunk 有完整元数据
- [ ] BM25 召回可用
- [ ] 向量召回可用
- [ ] 地理召回可用
- [ ] 模板召回可用
- [ ] RRF 融合可用
- [ ] Reranker 可选启用
- [ ] 回答展示来源和更新时间
- [ ] 用户私有 RAG 与公共 RAG 严格隔离
- [ ] 删除数据源后，对应向量同步删除
- [ ] 建立最小 RAG 评测集

---

# 阶段 5：长期 Memory 与个性化记忆体系

## 5.1 目标

建立可解释、可控、可删除的长期记忆系统。

## 5.2 Memory 类型

### Explicit 明确记忆

用户明确说：

```text
请记住我喜欢博物馆
```

处理：

```text
直接写入，高置信度
```

### Episodic 情景记忆

记录：

```text
用户接受过什么方案
拒绝过什么方案
哪天去了哪里
实际节奏如何
```

### Semantic 语义记忆

从多次行为归纳：

```text
用户偏好慢节奏
用户倾向靠近地铁的酒店
用户喜欢本地老店
```

### Scenario 场景记忆

按场景保存：

```text
独自旅行
亲子旅行
带父母旅行
情侣旅行
商务旅行
```

避免把亲子偏好错误应用到独自旅行。

## 5.3 Memory 写入规则

| 场景 | 处理 |
|---|---|
| 用户明确说“记住” | 写入 explicit memory |
| 用户表达稳定偏好 | 高置信度写入 |
| 用户接受 / 拒绝方案 | 写入 episodic memory |
| 多次出现相同倾向 | 合并为 semantic memory |
| 单次模糊推断 | 仅保留短期 |
| 敏感信息 | 默认不保存 |

## 5.4 Memory 冲突处理

规则：

```text
当前明确要求 > 当前旅行上下文 > 明确长期偏好 > 推断偏好
最近确认 > 旧记录
多场景分开保存
不简单覆盖旧值
```

示例：

```text
用户以前喜欢紧凑行程
但这次说“带孩子，不要太累”
```

本次行程必须使用当前约束，不应用旧偏好。

## 5.5 Memory 检索

使用：

```text
向量相似度
类别
场景
重要度
置信度
最近确认时间
过期时间
```

初始配置：

```text
初始召回数量：8
注入 Prompt 数量：5
最大注入 Token：1200
最低相关度：0.70
推断写入阈值：0.85
归纳所需最少证据数：2
```

## 5.6 用户控制

必须提供：

```text
查看 Memory
修改 Memory
删除单条 Memory
清空全部 Memory
关闭个性化
关闭长期 Memory
导出 Memory
```

删除时同步删除：

```text
memory_items
memory_evidence
memory_relations
embedding
```

## 5.7 阶段验收标准

- [ ] 用户明确要求记住的内容能保存
- [ ] 用户接受 / 拒绝行为能形成证据
- [ ] 多次行为能归纳为语义偏好
- [ ] 单次模糊行为不会写入长期 Memory
- [ ] 当前旅行约束优先于长期偏好
- [ ] 不同场景偏好分开保存
- [ ] Memory 检索有相关度阈值
- [ ] Prompt 注入有数量和 Token 限制
- [ ] 用户可以查看、修改、删除 Memory
- [ ] 用户可以关闭个性化
- [ ] 删除用户时 Memory 和向量全部清除

---

# 阶段 6：个性化推荐与行程生成优化

## 6.1 目标

让系统不只是“生成行程”，而是根据用户、预算、路线、时效、口碑进行可解释排序。

## 6.2 排序特征

```text
用户偏好匹配度
预算匹配度
路线可行性
景点口碑
开放状态
预约要求
天气适配
时效性
拥挤程度
多样性
用户历史拒绝记录
```

## 6.3 评分模型

第一版使用可解释线性加权：

```text
score =
  w1 * preference_match
+ w2 * budget_match
+ w3 * route_feasibility
+ w4 * popularity
+ w5 * freshness
+ w6 * weather_fit
+ w7 * diversity
- w8 * user_rejection_penalty
```

每个分数都必须可解释。

## 6.4 局部修改行程

基于 `activity_id` 修改，而不是重写整份行程。

支持：

```text
删除某个活动
替换某个活动
调整时间
更换城市内顺序
增加休息
减少步行
改成室内方案
```

修改后生成新的：

```text
trip_plan_version
```

## 6.5 确定性校验

行程生成后必须校验：

```text
时间不重叠
交通时间合理
营业时间匹配
闭馆日期排除
预算总和不超限
每日活动强度不超限
景点距离可接受
```

这些用普通代码校验，不交给 LLM。

## 6.6 阶段验收标准

- [ ] 推荐结果有可解释评分
- [ ] 用户偏好影响排序
- [ ] 预算约束影响排序
- [ ] 路线可行性影响排序
- [ ] 用户拒绝过的类型会被降权
- [ ] 支持基于 activity_id 的局部修改
- [ ] 修改后保留历史版本
- [ ] 时间冲突可以被确定性校验发现
- [ ] 预算超限可以被确定性校验发现
- [ ] 天气影响可以调整行程

---

# 阶段 7：FastAPI 后端建设

## 7.1 目标

把 CLI 能力升级成可给前端调用的 API 服务。

## 7.2 API 模块

```text
/auth
/users
/sessions
/messages
/trips
/trip-versions
/itinerary
/memory
/rag
/tools
/feedback
/health
```

## 7.3 核心 Endpoint

### 会话

```http
POST   /sessions
GET    /sessions
GET    /sessions/{session_id}
DELETE /sessions/{session_id}
```

### 对话

```http
POST /sessions/{session_id}/messages
GET  /sessions/{session_id}/messages
```

支持 SSE 流式返回。

### 行程

```http
GET    /trips
GET    /trips/{trip_id}
GET    /trips/{trip_id}/versions
POST   /trips/{trip_id}/refine
DELETE /trips/{trip_id}
```

### Memory

```http
GET    /memory
PATCH  /memory/{memory_id}
DELETE /memory/{memory_id}
DELETE /memory
POST   /memory/settings
```

### RAG

```http
POST /rag/documents
GET  /rag/documents
POST /rag/search
DELETE /rag/documents/{document_id}
```

### 工具

```http
GET /tools
GET /tools/health
POST /tools/{tool_name}/invoke
```

## 7.4 安全要求

```text
认证
授权
CORS 白名单
请求限流
输入校验
Secret 管理
日志脱敏
```

## 7.5 阶段验收标准

- [ ] FastAPI 服务可启动
- [ ] OpenAPI 文档可访问
- [ ] 会话和行程 API 可用
- [ ] 对话支持流式响应
- [ ] Memory 管理 API 可用
- [ ] RAG 上传和检索 API 可用
- [ ] 工具健康检查 API 可用
- [ ] API 层强制 user_id 隔离
- [ ] 敏感信息不出现在日志
- [ ] 有 API 集成测试

---

# 阶段 8：前端页面建设

## 8.1 目标

做一个可实际使用的旅行助手界面，而不是只有 CLI。

## 8.2 技术栈

```text
Vue 3
TypeScript
Vite
Pinia
Vue Router
AMap JS API
```

## 8.3 页面结构

### 首页 / 会话列表

```text
历史会话
新建会话
当前活动行程
用户设置
```

### 对话页

```text
左侧：会话列表
中间：聊天流
右侧：当前行程概览
```

支持：

```text
流式输出
工具执行状态
来源引用
澄清问题
用户反馈按钮
```

### 行程规划页

```text
地图
日程时间轴
每日活动
交通段
天气提示
预算统计
版本对比
```

### Memory 管理页

```text
查看长期记忆
编辑
删除
关闭个性化
导出
```

### RAG 知识管理页

```text
上传文档
查看来源
查看授权状态
删除文档
查看索引状态
```

### 设置页

```text
模型设置
地图 Key
个性化开关
长期记忆开关
敏感信息策略
```

## 8.4 地图能力

使用高德 JS API：

```text
POI 标点
活动连线
路线展示
城市定位
每日轨迹颜色区分
```

## 8.5 阶段验收标准

- [ ] 用户可以登录或使用本地身份
- [ ] 用户可以创建多个会话
- [ ] 页面刷新后会话可以恢复
- [ ] 对话支持流式输出
- [ ] 行程在地图和时间轴中展示
- [ ] 用户可以局部修改活动
- [ ] 用户可以查看历史版本
- [ ] Memory 可查看、编辑、删除
- [ ] RAG 来源可展示
- [ ] 前端不会越权访问其他用户数据

---

# 阶段 9：观测、评测与生产化

## 9.1 目标

让系统从 Demo 变成可长期维护的服务。

## 9.2 日志与追踪

```text
结构化日志
请求 ID
会话 ID
Trip ID
工具调用链
Token 消耗
延迟
错误码
```

## 9.3 评测体系

### RAG 评测

```text
Recall@K
Precision@K
nDCG
引用准确率
来源可追溯率
```

### 行程评测

```text
时间冲突率
预算超限率
路线不可行率
用户修改次数
用户接受率
```

### Memory 评测

```text
错误写入率
错误召回率
用户修正率
冲突处理正确率
```

## 9.4 部署

```text
Docker Compose
PostgreSQL
Redis
FastAPI
前端 Nginx
可选对象存储
```

## 9.5 阶段验收标准

- [ ] 有结构化日志
- [ ] 有请求级 tracing
- [ ] 工具调用耗时和错误可见
- [ ] RAG 有评测脚本
- [ ] 行程质量有评测脚本
- [ ] Memory 有隐私测试
- [ ] Docker Compose 可一键启动
- [ ] 生产配置不包含真实 Secret
- [ ] 全部测试通过

---

# 推荐实施顺序

```text
阶段 1：数据库与 user/session/trip 隔离
阶段 2：上下文管理与 PostgreSQL Checkpoint
阶段 3：MCP Gateway 与 12306 / 高德工具统一
阶段 4：RAG 知识库与多路召回
阶段 5：长期 Memory
阶段 6：个性化排序与局部行程修改
阶段 7：FastAPI 后端
阶段 8：Vue 3 前端
阶段 9：观测、评测与生产化
```

依赖关系：

- 阶段 1 是地基，必须最先做
- 阶段 2 依赖数据库
- 阶段 4 和阶段 5 依赖数据库和 Embedding
- 阶段 6 依赖 MCP、RAG、Memory
- 阶段 7、8 在核心能力稳定后做
- 阶段 9 贯穿始终，最后集中补强

---

# 第一批开工任务：阶段 1

## 1. 建立数据库基础工程

新增目录：

```text
db/
├─ base.py
├─ engine.py
├─ models.py
├─ repositories/
├─ migrations/
```

引入依赖：

```text
sqlalchemy
alembic
asyncpg
psycopg
pgvector
```

## 2. 建立核心 ORM 模型

先做最小可运行集合：

```text
users
chat_sessions
chat_messages
trips
trip_plan_versions
memory_items
memory_evidence
rag_sources
rag_documents
rag_chunks
tool_calls
provider_health
```

## 3. 写 Alembic migration

支持：

```text
init
upgrade
downgrade
```

## 4. 写 Repository 层

重点实现：

```text
UserRepository
SessionRepository
MessageRepository
TripRepository
PlanVersionRepository
MemoryRepository
RagRepository
ToolCallRepository
```

所有 Repository 强制：

```text
user_id
session_id
trip_id
```

## 5. 写隔离测试

覆盖：

```text
用户 A 不能读用户 B 数据
会话 A 不能读会话 B 数据
Trip A 不能读 Trip B 数据
删除用户后级联删除
公共 RAG 与私有 RAG 检索隔离
```

## 6. 迁移现有 JSON 数据

写迁移脚本：

```text
memory_data/users/*.json → users
memory_data/sessions/*.json → chat_sessions / chat_messages
memory_data/trips/*.json → trips / trip_plan_versions
```

迁移时保留：

```text
原 user_id
原 session_id
原 trip_id
原时间
```

---

# 最终系统分层

```text
1. 多智能体协作层
   LangGraph 五节点 + Planner + Executor + Summarizer

2. 实时工具层
   高德 / 天气 / 铁路 MCP Gateway + 统一 ToolResult

3. 知识层
   官方事实 + 授权攻略 + 模板 + BM25 / 向量 / 地理 / 模板召回 + RRF + Reranker

4. 记忆层
   短期 Checkpoint + 长期 Memory + 用户偏好 + 冲突处理 + 隐私控制

5. 应用层
   FastAPI + Vue 3 + 地图 + 行程编辑 + Memory 管理 + RAG 管理
```
