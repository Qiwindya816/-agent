# 智能旅游助手后续改进规划

> 项目：[zjrlalala/travel-agent](https://github.com/zjrlalala/travel-agent)  
> 参考：[Hello-Agents 第十三章：智能旅行助手](https://github.com/datawhalechina/hello-agents/blob/main/docs/chapter13/%E7%AC%AC%E5%8D%81%E4%B8%89%E7%AB%A0%20%E6%99%BA%E8%83%BD%E6%97%85%E8%A1%8C%E5%8A%A9%E6%89%8B.md)  
> 文档性质：规划方案，暂不实施  
> 整理日期：2026-08-18

## 1. 总体判断

当前项目已经具备一个可运行的多 Agent 原型，包含 LangGraph 工作流、MCP 工具、RAG、用户画像和聊天记录等模块，但暂时还不能算作可靠的旅游推荐产品。

后续建议先补齐结构化数据、工具执行、会话状态和评测基础，再实现多源召回、混合 RAG、地图交互，最后才接入商业推荐。

如果一开始同时接入高德、百度、美团、小红书和广告系统，数据格式、工具错误和推荐质量会很难控制。更稳妥的 MVP 是：

> 高德地图 + 官方/用户授权攻略 + 结构化行程 + 可编辑地图

## 2. 现有项目实现梳理

### 2.1 当前工作流

```text
用户输入
  ↓
Main Agent：旅游 / 闲聊 / 反馈分类
  ↓
Planner Agent：提取目的地、出发地、预算、日期等信息
  ↓
Executor Agent
  ├─ 简单问题：ReAct，最多循环 8 次
  └─ 完整规划：DeepSeek 先制定工具调用计划，再顺序执行
  ↓
Summarizer Agent：合并 RAG、MCP 和用户画像
  ↓
文本答案
```

主要实现位置：

- [`graph/workflow.py`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/graph/workflow.py)
- [`agent_nodes/planner_agent.py`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/agent_nodes/planner_agent.py)
- [`agent_nodes/executor_agent.py`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/agent_nodes/executor_agent.py)
- [`agent_nodes/summarizer_agent.py`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/agent_nodes/summarizer_agent.py)

### 2.2 已有优点

- 已拆分 Main、Planner、Executor、Summarizer、Feedback Agent。
- 有简单 ReAct 和复杂 Plan-then-Execute 两种模式。
- 已接入 MCP、Chroma、用户画像和 SQLite 聊天记录。
- 有文档上传和增量导入的雏形。
- 用户反馈可以更新偏好画像。
- 已具备 Streamlit 交互界面，方便原型验证。

### 2.3 当前主要问题

#### 2.3.1 工具声明与执行不一致

[`tools/tool_registry.py`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/tools/tool_registry.py) 声明了以下工具：

- 高德地理编码
- 高德驾车路线
- 航班查询
- DeepSeek R1 分析
- 火车查询
- 天气、酒店和 POI 查询

但 [`execute_tool`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/agent_nodes/executor_agent.py#L23) 没有实现所有分支。“火车查询会自动对比自驾”的描述也没有落实。

#### 2.3.2 MCP 错误处理不足

- MCP 初始化失败时会被静默忽略。
- `required` 配置没有真正用于启动检查。
- 缺少服务健康状态、熔断和降级策略。
- 用户可能得到一个看似正常、实际缺少实时数据的答案。

#### 2.3.3 RAG 仍是单路相似度检索

当前 [`rag_tool.py`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/tools/rag_tool.py#L367) 主要是：

```text
用户查询 → Chroma similarity_search → Top 3 → 截断内容 → 交给 LLM
```

尚未包含：

- BM25 关键词检索
- 元数据过滤
- 多路召回融合
- Reranker 重排
- 来源质量评分
- 时效性过滤
- 引用验证
- 检索效果评测

#### 2.3.4 聊天记录不等于 Agent 长期记忆

SQLite 中的历史消息可以显示在页面上，但恢复或切换会话后，没有完整注入 LangGraph 运行状态。

同时，[`app.py`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/app.py#L319) 每次收到新问题都会重置 Planner、Executor 和 Summarizer 上下文。已有的历史压缩函数也没有真正接入主工作流。

#### 2.3.5 输出缺少结构化数据

目前最终结果主要是 Markdown 文本，缺少稳定的数据模型，例如：

- `TripPlan`
- `DayPlan`
- `POI`
- `Hotel`
- `Route`
- `Budget`

因此很难实现：

- 地图标点和路线绘制
- 拖拽调整景点顺序
- 删除或替换单个景点
- 局部重新算路
- 自动更新预算
- PDF 或图片导出

#### 2.3.6 配置和文档存在不一致

README 表示 `.env` 和向量数据库目录可配置，但 [`settings.py`](https://github.com/zjrlalala/travel-agent/blob/main/multi-agents/config/settings.py) 仍硬编码了部分路径，部分环境变量没有真正生效。

## 3. Hello-Agents 第十三章可借鉴内容

Hello-Agents 第十三章最值得参考的不是单纯增加 Agent 数量，而是以下产品化思路：

- 使用 Pydantic 建立结构化后端数据模型。
- 使用 FastAPI 提供稳定接口。
- 使用 Vue 3 + TypeScript 构建交互式前端。
- 在地图上展示景点位置和路线。
- 支持行程编辑、预算联动和导出。
- 多个 Agent 共享 MCP 实例，减少资源浪费。
- 将不需要智能决策的步骤做成普通服务，而不是全部封装成 Agent。

## 4. 建议的目标架构

```text
Web / 移动端
├─ 对话区域
├─ 结构化行程编辑器
├─ 地图与路线
└─ 推荐 / 广告独立展示
        ↓
FastAPI 应用层
├─ 会话 API
├─ 用户与画像 API
├─ 行程 API
├─ 推荐解释与反馈 API
└─ SSE / WebSocket 进度推送
        ↓
LangGraph 协调层
├─ 需求理解与槽位补全
├─ 候选召回
├─ 行程规划
├─ 校验与反思
├─ 用户反馈处理
└─ 后续问题生成
        ↓
能力服务层
├─ MCP Provider Gateway
├─ 混合 RAG
├─ POI 去重与归一化
├─ 路线优化与预算计算
└─ 个性化排序
        ↓
数据层
├─ PostgreSQL：用户、行程、商家
├─ Redis：缓存、限流、任务状态
├─ pgvector / Qdrant：向量检索
├─ 对象存储：原始文档
└─ LangGraph Checkpoint：会话状态
```

### 4.1 LLM 与普通代码的职责边界

适合交给 LLM：

- 理解自然语言需求
- 提取用户约束
- 生成查询词
- 解释推荐原因
- 生成自然语言行程说明
- 根据反馈理解用户修改意图

适合交给确定性代码：

- 价格计算
- 预算汇总
- 时间冲突检测
- 距离计算
- 坐标转换
- POI 去重
- 营业时间判断
- 路线排序
- 推荐打分
- 广告频控

## 5. 分阶段改进计划

| 阶段 | 主要工作 | 交付结果 |
|---|---|---|
| P0 基线治理 | 修复工具声明与执行不一致、配置路径和错误吞没；补健康检查与测试 | 当前能力真实可用，错误可见 |
| P1 数据契约 | 定义 TripRequest、POI、Route、Hotel、DayPlan、Budget、TripPlan | Agent 输出稳定 JSON |
| P2 地图多源召回 | 高德、百度适配器；POI 归一化、坐标转换、去重、路线规划和缓存 | 多来源候选池与可解释排序 |
| P3 混合 RAG | 合法数据采集、结构化切块、BM25 + 向量 + 元数据 + 重排 | 可引用、可评测的攻略检索 |
| P4 持续交互 | Checkpoint 会话记忆、槽位补全、后续问题、局部重规划 | 类似 ChatGPT 的连续旅游对话 |
| P5 产品界面 | FastAPI + Vue/TypeScript；地图、拖拽、增删景点、预算联动和导出 | 完整可交互行程产品 |
| P6 商业推荐 | 商家后台、优惠核验、广告独立召回和披露、频控、退出机制 | 合规商业化试点 |
| P7 评测与运营 | 离线测试集、线上指标、链路追踪和 A/B 测试 | 可持续优化 |

## 6. P0：现有系统基线治理

在新增功能之前，建议先完成以下工作。

### 6.1 工具系统

- 为工具注册和实际执行建立唯一来源，避免维护两套定义。
- 补齐 `gaode_geo`、`gaode_driving`、`flight_query`、`r1_analysis` 的执行逻辑。
- 未实现的工具暂时不要暴露给 LLM。
- 工具参数使用 Pydantic 或 JSON Schema 严格验证。
- 工具返回统一成：

```json
{
  "success": true,
  "provider": "amap",
  "tool": "route_driving",
  "data": {},
  "error": null,
  "fetched_at": "2026-08-18T10:00:00+08:00",
  "expires_at": "2026-08-18T10:10:00+08:00"
}
```

### 6.2 MCP 可靠性

- 启动时执行必需服务健康检查。
- 对必需和可选 MCP 分别处理。
- 增加超时、重试、限流、熔断和降级。
- 禁止静默吞掉连接失败。
- 记录每次工具调用的耗时、成功状态和数据来源。
- 增加工具白名单，避免 LLM 任意调用未知工具。

### 6.3 工程配置

- 统一 `.env` 的实际位置和 README 描述。
- 所有目录都可通过环境变量覆盖。
- API Key 不进入仓库。
- 锁定依赖版本，补充缺失的 PDF 等依赖。
- 增加开发、测试、生产三套配置。
- 删除仓库中的运行数据库和 IDE 配置等非必要文件。

### 6.4 测试

- Planner 信息提取测试。
- 工具参数与返回值测试。
- MCP 失败和重试测试。
- RAG 空库、重复导入和检索测试。
- LangGraph 路由测试。
- 端到端典型旅行问题测试。

## 7. P1：建立结构化旅行数据模型

### 7.1 建议模型

#### TripRequest

```text
origin
destinations
start_date / end_date
travelers
budget
preferences
transport_preferences
hotel_preferences
mobility_constraints
must_visit
avoid
```

#### POI

```text
poi_id
provider
provider_poi_id
name
aliases
category
longitude / latitude
coordinate_system
address / district
rating / review_count
price_level / ticket_price
opening_hours
tags
source_url
updated_at
confidence
```

#### DayPlan

```text
date
city
activities
routes
meals
hotel
daily_budget
warnings
```

#### TripPlan

```text
trip_id
request
days
budget_summary
weather
transport_options
sources
assumptions
warnings
version
```

### 7.2 版本化

每次用户修改行程时生成新版本：

```text
TripPlan v1
  ↓ 删除景点
TripPlan v2
  ↓ 调整第二天顺序
TripPlan v3
```

这样可以支持撤销、重做、比较和审计。

## 8. P2：地图 MCP 与多源召回

### 8.1 Provider 接入策略

第一期建议接入：

- 高德：POI、天气、地理编码、驾车、步行、公交。
- 百度：第二 POI 和路线来源。
- 12306：城际铁路。
- 航班：取得稳定合法数据接口后接入。
- 美团：作为商务授权后的可选 Provider。

参考文档：

- [高德 POI 搜索](https://lbs.amap.com/api/webservice/guide/api/search/)
- [高德路径规划](https://lbs.amap.com/api/webservice/guide/api/newroute)
- [百度 Web 服务 API](https://lbsyun.baidu.com/faq/api?title=webapi)
- [美团生态开放平台](https://openapi.meituan.com/)

美团公开页面不能证明存在面向任意旅游应用开放的通用门店、评价和优惠检索接口，因此不应把它作为 MVP 的必要依赖。需要先确认商务授权、数据范围、调用限制和展示要求。

### 8.2 Provider Gateway

为所有地图和本地生活数据提供统一接口：

```python
class POIProvider:
    async def search_pois(...): ...
    async def get_poi_detail(...): ...
    async def geocode(...): ...
    async def route(...): ...
```

Agent 不直接依赖“高德工具名”或“百度工具名”，而是调用统一业务工具：

- `search_attractions`
- `search_hotels`
- `search_restaurants`
- `get_weather`
- `plan_route`

### 8.3 坐标和数据归一化

必须处理：

- WGS-84
- GCJ-02
- BD-09
- 同名景点和别名
- 连锁门店与分店
- 多来源评分口径不同
- 地址不一致
- 更新时间不一致
- 营业状态冲突

### 8.4 POI 去重

可以综合以下信息：

- 标准化名称
- 别名
- 地址
- 电话
- 经纬度距离
- 分类
- Provider POI ID

不能只按名称去重，例如不同城市可能都有“人民公园”。

### 8.5 推荐排序

推荐过程分两步：

1. 硬过滤
2. 软打分

硬过滤包括：

- 日期和营业时间不匹配
- 超出预算
- 距离不合理
- 已闭园或暂停营业
- 不符合行动能力约束
- 用户明确拒绝的类别

建议初始评分：

```text
总分 =
  用户偏好匹配       25%
+ 时间与路线可行性   20%
+ 口碑可信度         15%
+ 性价比             15%
+ 时效与可用性       10%
+ 天气/拥挤/安全适配 10%
+ 行程多样性          5%
```

权重可以按画像调整：

- 亲子游：安全、距离和儿童设施权重增加。
- 老人游：步行距离、无障碍和休息时间权重增加。
- 特种兵旅行：景点密度和路线效率权重增加。
- 低预算：价格和免费景点权重增加。
- 文化游：博物馆、古迹和内容深度权重增加。

## 9. P3：RAG 改造方案

### 9.1 数据来源优先级

1. 文旅局、景区、博物馆和交通部门官方内容。
2. 用户主动上传或收藏的攻略。
3. 旅行社、酒店和商家授权内容。
4. 获得许可的第三方内容接口。
5. 平台内容只能在官方授权或用户主动提供的前提下使用。

### 9.2 小红书内容处理原则

不建议将“批量爬取小红书帖子”作为正式产品的默认数据管道。

原因包括：

- 平台协议和访问限制。
- 内容版权和二次使用范围。
- 用户昵称、头像、位置等个人信息。
- 内容删除后知识库同步删除的问题。
- 反爬和数据稳定性。
- 笔记内容可能包含软广告和虚假评价。

可选的合法路径：

- 用户主动提交笔记链接，仅用于个人行程分析。
- 使用获得授权的数据服务。
- 与平台或内容方合作。
- 只保存结构化事实和来源链接，不复制完整原文。
- 为来源设置删除和更新机制。

参考：[小红书分享开放平台](https://agora.xiaohongshu.com/)

### 9.3 知识库分类

- 城市总攻略
- 1 日、2 日、3 日、5 日行程模板
- 亲子、老人、情侣和独旅攻略
- 美食、博物馆、自然和夜游
- 避坑、预约、交通和季节信息
- 酒店商圈与交通枢纽
- POI 事实卡
- 用户历史行程与反馈

### 9.4 数据处理流程

```text
合法数据源
 → 原始数据存储
 → 清洗与正文提取
 → 个人信息和广告内容处理
 → 去重
 → 事实及结构提取
 → 按城市/主题/天数/每日计划/POI 切块
 → Embedding
 → 向量索引 + BM25 索引
 → 增量更新和删除同步
```

### 9.5 元数据

每个知识块至少保存：

```text
source_id
source_type
source_url
title
author_or_organization
license_or_authorization
publish_time
fetch_time
city / district
poi_ids
travel_days
season
traveler_type
budget_level
theme
content_quality
commercial_content
```

### 9.6 混合检索链路

```text
用户问题
 → 意图、地点、日期、人群提取
 → 查询改写
 → 并行召回
    ├─ BM25 关键词检索
    ├─ 向量语义检索
    ├─ 元数据过滤
    ├─ 地理范围检索
    ├─ 行程模板召回
    └─ 用户记忆召回
 → RRF 融合
 → Cross-Encoder / LLM 重排
 → 去重和时效过滤
 → 返回来源、日期和置信度
```

### 9.7 RAG 评测

- Recall@K
- Precision@K
- MRR
- nDCG
- 引用正确率
- 来源覆盖率
- 事实一致性
- 过期信息比例
- 无答案时是否能正确拒答

## 10. P4：持续交互和 Agent 记忆

### 10.1 回答后的快捷问题

每次回答后生成 2～4 个与当前状态相关的建议，例如：

- 是否生成完整三日行程？
- 是否比较高铁和自驾？
- 是否查看地图路线？
- 是否按亲子游重新推荐？
- 是否把预算控制在 2000 元以内？

建议由规则产生候选，再由 LLM 润色，减少无关问题。

### 10.2 槽位补全

缺少信息时，一次只询问最关键的问题。

示例：

```text
用户：国庆想去苏州玩。
助手：可以。你从哪里出发？这会影响高铁和自驾方案。
用户：上海。
助手：预计玩几天？如果还没决定，我可以先给你 2 日和 3 日两个版本。
```

### 10.3 局部重规划

用户说以下内容时，不应重新执行全部工具：

- “第二天太累了”
- “不要寺庙”
- “把酒店换便宜一点”
- “晚上不想安排活动”
- “加入苏州博物馆”

应识别影响范围，仅重新处理对应日期、路线或预算。

### 10.4 状态分类

需要区分：

- 当前会话消息
- 当前旅行计划
- 本次旅行临时偏好
- 用户长期偏好
- 已拒绝候选
- 工具调用结果及有效期
- 行程历史版本

不能把一次“这次不想去寺庙”自动变成永久的“用户讨厌寺庙”。

### 10.5 LangGraph Checkpoint

使用持久化 Checkpoint 保存工作流状态，使会话恢复后能够继续修改原计划，而不只是重新显示聊天文本。

## 11. P5：前后端与地图交互

### 11.1 后端

建议从 Streamlit 原型逐步迁移为 FastAPI：

```text
POST   /api/trips/plan
GET    /api/trips/{trip_id}
PATCH  /api/trips/{trip_id}
POST   /api/trips/{trip_id}/replan
POST   /api/trips/{trip_id}/feedback
GET    /api/trips/{trip_id}/events
POST   /api/trips/{trip_id}/export
```

### 11.2 前端

推荐 Vue 3 + TypeScript，主要页面包括：

- 首页需求表单
- 对话页
- 规划进度页
- 行程结果页
- 地图页
- 行程编辑页
- 用户偏好页
- 历史行程页

### 11.3 地图交互

- 按天显示不同颜色的景点标记。
- 绘制日内路线。
- 拖拽调整顺序。
- 删除、替换和新增景点。
- 修改后重新计算距离、时间和预算。
- 展示地图与行程列表联动。
- 显示营业时间冲突和超预算警告。

### 11.4 导出

- PDF
- 长图
- 日历文件 ICS
- 可分享链接
- 地图导航链接

## 12. P6：商业推荐方案

### 12.1 不建议隐藏式软广告

不建议让用户无法区分自然推荐与广告。商业出价也不应直接加入自然推荐分数。

推荐采用双通道：

```text
自然推荐候选 → 自然排序 → 自然推荐区

合作商家候选
 → 相关性与质量门槛
 → 广告审核
 → 频控
 → 合作优惠区
```

### 12.2 商业推荐准入条件

- 距离合理
- 正常营业
- 优惠真实且未过期
- 符合用户预算和偏好
- 评分和投诉率达到标准
- 不破坏路线合理性
- 广告主资质审核通过

### 12.3 展示要求

- 明确标识“广告”“合作商家”或“含推广”。
- 展示推荐原因。
- 展示原价、优惠价、有效期和核验时间。
- 支持一键关闭商业推荐。
- 支持非个性化推荐。
- 限制每个日程和页面的商业位数量。
- 不因用户画像而实施不合理差别价格。

参考：

- [《互联网广告管理办法》](https://www.samr.gov.cn/cms_files/filemanager/1647978232/attach/20234/W020230320579023662253.pdf?fileName=W020230320579023662253.pdf)
- [《个人信息保护法》相关规定](https://www.samr.gov.cn/wljys/gzzd/art/2023/art_3ef1e889c1e644d4b65b5f5c7f432386.html)

### 12.4 商家后台需要的功能

- 商家注册和资质审核
- 门店绑定
- 优惠活动创建
- 活动有效期和库存
- 广告素材审核
- 预算和频控
- 投放区域和人群设置
- 曝光、点击和核销统计
- 用户投诉和下架机制
- 投放日志与广告档案

## 13. 需要配置的内容

### 13.1 模型与 Agent 配置

```text
LLM_PROVIDER
LLM_MODEL
LLM_API_KEY
LLM_BASE_URL
LLM_TIMEOUT
LLM_MAX_RETRIES
EMBEDDING_MODEL
RERANKER_MODEL
MAX_AGENT_STEPS
MAX_TOOL_CALLS
MAX_REQUEST_COST
LANGGRAPH_CHECKPOINT_URL
PROMPT_VERSION
```

### 13.2 MCP 与 Provider 配置

每个服务配置：

- Provider 名称
- MCP URL 或本地启动命令
- 传输方式
- API Key
- 工具白名单
- 工具参数 Schema
- 是否必需
- 超时
- 重试
- 并发限制
- 每分钟限流
- 熔断阈值
- 缓存有效期
- 健康检查
- 授权和展示限制

示例：

```yaml
providers:
  amap:
    enabled: true
    required: true
    api_key_env: AMAP_WEB_SERVICE_KEY
    timeout_seconds: 15
    max_retries: 2
    rate_limit_per_minute: 100
    tools:
      - poi_search
      - geocode
      - weather
      - route_driving
      - route_walking

  baidu:
    enabled: false
    required: false
    api_key_env: BAIDU_MAP_AK
```

### 13.3 RAG 配置

```text
VECTOR_DB_URL
VECTOR_COLLECTION
BM25_INDEX_PATH
OBJECT_STORAGE_URL
CHUNK_STRATEGY
DENSE_TOP_K
BM25_TOP_K
RRF_TOP_K
RERANK_TOP_K
MIN_RELEVANCE_SCORE
MAX_DOCUMENT_AGE
SOURCE_ALLOWLIST
DATA_RETENTION_DAYS
```

### 13.4 排序配置

```yaml
ranking:
  preference: 0.25
  route_feasibility: 0.20
  quality: 0.15
  value_for_money: 0.15
  freshness: 0.10
  safety_weather_crowding: 0.10
  diversity: 0.05

sponsored:
  enabled: false
  max_items_per_day: 1
  min_relevance_score: 0.75
  require_ad_label: true
  allow_personalization: false
```

### 13.5 基础设施配置

- PostgreSQL
- Redis
- pgvector 或 Qdrant
- 对象存储
- 用户认证
- Secret Manager
- 日志脱敏
- OpenTelemetry 或 LangSmith
- 错误告警
- 数据备份
- 用户数据删除任务

## 14. 需要掌握的知识

### 14.1 Agent 与后端

- Python 异步编程
- FastAPI
- Pydantic
- LangChain
- LangGraph 状态机
- Checkpoint
- Human-in-the-loop
- 结构化输出
- Prompt 版本管理

### 14.2 MCP

- MCP 传输协议
- 工具发现
- JSON Schema
- 工具白名单
- 超时和重试
- 限流与熔断
- MCP 服务健康检查
- 工具结果标准化

### 14.3 地图与路线

- 高德和百度地图 API
- 地理编码和逆地理编码
- WGS-84、GCJ-02、BD-09
- POI 去重与实体对齐
- 地理空间索引
- 路径规划
- TSP / VRP 基础
- 营业时间和时间窗约束

### 14.4 RAG 与搜索

- 文档清洗和结构化切块
- BM25
- Embedding
- 向量数据库
- 元数据过滤
- RRF
- Cross-Encoder Reranker
- Query Rewrite
- 引用和事实验证
- RAG 评测

### 14.5 推荐系统

- 候选召回
- 粗排和精排
- 特征工程
- 多样性和去重
- 冷启动
- 用户画像
- 可解释推荐
- A/B 测试
- 商业广告与自然推荐隔离

### 14.6 前端

- Vue 3
- TypeScript
- 地图 JavaScript API
- SSE / WebSocket
- 拖拽排序
- 状态管理
- PDF 和图片导出

### 14.7 数据与合规

- 数据授权和版权
- 个人信息保护
- 自动化决策透明度
- 广告标识和审核
- 日志脱敏
- 数据保留与删除
- 商家资质和广告档案

## 15. 验收与评测指标

### 15.1 工具系统

- 工具参数校验通过率
- MCP 调用成功率
- P50 / P95 调用时延
- 降级成功率
- 数据更新时间

### 15.2 行程质量

- 时间冲突率
- 营业时间冲突率
- 路线绕行比例
- 预算偏差
- 用户删除和替换比例
- 行程保存、导出和分享率

### 15.3 RAG

- Recall@10
- nDCG@10
- 引用正确率
- 来源覆盖率
- 过期信息比例
- 幻觉率

### 15.4 交互

- 完成一份行程所需轮数
- 澄清问题有效率
- 快捷问题点击率
- 局部重规划成功率
- 会话恢复成功率

### 15.5 商业推荐

- 广告标识合规率必须为 100%
- 优惠核验成功率
- 用户关闭率
- 投诉率
- 广告对自然推荐质量的影响
- 核销率

不能只以广告点击率作为优化目标。

## 16. 推荐实施顺序

建议严格按照以下顺序推进：

1. 修复现有工具、配置和错误处理。
2. 建立结构化 `TripPlan` 数据模型。
3. 完成高德单源闭环。
4. 加入百度，实现多源归一化、去重和评分。
5. 建设合法、可引用、可评测的混合 RAG。
6. 实现持久会话和局部重规划。
7. 升级 FastAPI + Vue 地图交互。
8. 达到稳定质量后，再进行商业推荐试点。

## 17. 建议的第一版 MVP 范围

第一版建议只完成：

- 高德 POI、天气和路线。
- 12306 火车查询。
- 官方和用户授权攻略 RAG。
- 结构化 1～3 日行程。
- 预算汇总。
- 地图标点和路线绘制。
- 用户删除、替换和调整景点顺序。
- 会话持续修改。
- 结果引用来源和更新时间。

第一版暂不做：

- 未取得授权的平台内容批量爬取。
- 美团通用数据接入假设。
- 隐藏式软广告。
- 自动订票、自动下单和支付。
- 过于复杂的多城市全局优化。

完成这一版后，再根据用户真实使用数据决定是否扩展更多 Provider、复杂路线和商业推荐。
