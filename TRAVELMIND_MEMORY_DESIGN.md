# TravelMind 第五阶段记忆体系设计

> 目标：建立短期记忆、长期记忆和程序记忆的分层体系，支持个性化推荐、可解释记忆、用户控制和隐私删除。
> 本设计将长期记忆分为三类：
>
> - 语义记忆（Semantic Memory）：稳定偏好和事实
> - 情景记忆（Episodic Memory）：历史旅行、接受/拒绝行为和具体经历
> - 程序记忆（Procedural Memory）：用户完成任务的操作偏好和流程规则

---

## 1. 总体分层

```text
用户输入
  ↓
短期记忆 ShortTermMemory
  ├─ 当前旅行约束
  ├─ 当前会话对话
  ├─ 当前行程版本
  ├─ 未解决问题
  ├─ 本轮工具结果
  └─ 会话摘要
  ↓
长期记忆 LongTermMemory
  ├─ 语义记忆 Semantic
  │  └─ 稳定偏好、事实、场景偏好
  ├─ 情景记忆 Episodic
  │  └─ 历史旅行、接受、拒绝、反馈
  └─ 程序记忆 Procedural
     └─ 操作流程、交互偏好、任务习惯
```

---

## 2. 短期记忆设计

### 2.1 定位

短期记忆只服务当前会话和当前 trip。

生命周期：

```text
会话创建 → 会话活跃 → 会话归档
```

默认不进入长期记忆。

### 2.2 状态字段

短期记忆包含：

```text
current_destination
current_departure_city
current_dates
current_travel_days
current_travelers
current_budget
confirmed_constraints
open_questions
temporary_preferences
rejected_candidates
current_itinerary_version
tool_results
conversation_summary
```

### 2.3 存储

当前已有：

```text
chat_sessions.agent_state
trips.agent_state
LangGraph checkpoints
chat_messages
```

第五阶段新增：

```text
short_term_memory
```

作为 `chat_sessions` 中的结构化字段，避免把所有短期状态都塞进完整 `agent_state`。

### 2.4 上下文注入优先级

```text
1. 用户本轮输入
2. 当前旅行硬约束
3. 当前行程版本
4. 未解决问题
5. 最近 N 轮对话
6. 工具实时结果
7. 旧会话摘要
8. 语义记忆
9. 情景记忆
10. 程序记忆
11. RAG 知识
```

---

## 3. 长期记忆分类

## 3.1 语义记忆 Semantic Memory

### 定义

从多次行为或明确表达中归纳出的稳定偏好、事实和规则。

### 示例

```text
用户喜欢博物馆
用户偏好靠近地铁的酒店
用户不喜欢行程太紧凑
用户平均每次旅行预算 5000 元
用户亲子旅行时偏好室内景点
```

### 来源

```text
用户明确说“请记住”
用户多次表达同一偏好
多次行为归纳
```

### 写入规则

| 证据类型 | 写入方式 |
|---|---|
| 用户明确要求记住 | explicit，confidence=0.98 |
| 用户明确表达稳定偏好 | semantic，confidence>=0.85 |
| 两次以上行为一致 | semantic，confidence>=0.75 |
| 单次模糊推断 | 不写长期记忆 |

### 字段

```text
memory_type = semantic
category
statement
structured_value
scope
importance
confidence
evidence_count
embedding
```

---

## 3.2 情景记忆 Episodic Memory

### 定义

具体旅行、具体选择和具体反馈的记忆。

### 示例

```text
2026-10 北京三日游，用户接受了故宫
2026-10 北京三日游，用户拒绝了夜爬长城
2026-08 成都两日游，用户说第三天太累
2026-08 成都两日游，用户选择人民公园茶馆
```

### 来源

```text
用户接受方案
用户拒绝方案
用户修改行程
用户事后反馈
历史行程记录
```

### 写入规则

```text
用户明确接受/拒绝 → 写入 episodic
用户修改活动 → 写入 episodic
用户给出反馈 → 写入 episodic
单次行为不自动归纳为 semantic
```

### 字段

```text
memory_type = episodic
category = accepted | rejected | modified | feedback | trip_event
structured_value = {
  trip_id,
  session_id,
  activity_id,
  destination,
  date,
  action,
  reason
}
```

---

## 3.3 程序记忆 Procedural Memory

### 定义

用户完成任务的操作流程、交互偏好和任务习惯。

### 示例

```text
用户习惯先看预算再定行程
用户希望先给三个候选目的地
用户喜欢按天查看行程
用户修改行程时希望只修改某个活动
用户查询火车票时习惯先查车站
用户对地图结果更信任
```

### 来源

```text
用户明确表达流程偏好
用户反复执行相同操作序列
用户对交互方式的反馈
```

### 写入规则

```text
用户明确要求“以后都这样做” → procedural
多次出现相同操作序列 → procedural
单次操作路径 → 不写长期程序记忆
```

### 字段

```text
memory_type = procedural
category = workflow | interaction | output_format | tool_sequence
structured_value = {
  trigger,
  preferred_action,
  sequence,
  constraints
}
```

---

## 4. Memory 类型总表

| 类型 | 中文名 | 保存内容 | 写入阈值 | 是否参与推荐排序 |
|---|---|---|---|---|
| semantic | 语义记忆 | 稳定偏好、事实 | 明确表达或多次证据 | 是 |
| episodic | 情景记忆 | 具体旅行行为 | 接受/拒绝/修改/反馈 | 是 |
| procedural | 程序记忆 | 操作和流程偏好 | 明确要求或重复行为 | 间接影响 |
| explicit | 显式记忆 | 用户明确要求记住 | 用户明确指令 | 是 |

当前数据库 `memory_type` 使用字符串，可平滑支持以上类型，不需要修改表结构。

---

## 5. 数据模型调整

## 5.1 现有表

当前已有：

```text
memory_items
memory_evidence
```

### `memory_items`

已支持：

```text
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
first_observed_at
last_confirmed_at
expires_at
```

### 需要新增

```text
embedding vector(1024)
embedding_text
```

`embedding_text` 用于保存生成向量时的原文，方便重新向量化。

### 建议索引

```text
HNSW(memory_items.embedding)
user_id + memory_type + status
user_id + scope + status
```

## 5.2 `memory_evidence`

当前已有：

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

### 建议新增

```text
evidence_type
confidence
```

用于区分：

```text
explicit_statement
inferred_behavior
accepted_action
rejected_action
workflow_pattern
```

---

## 6. 记忆写入流程

```text
用户输入
→ FeedbackAgent 提取
→ MemoryCandidateClassifier
   ├─ 短期偏好 → ShortTermMemory
   ├─ 明确记忆指令 → explicit memory
   ├─ 稳定偏好 → semantic memory
   ├─ 行为事件 → episodic memory
   └─ 流程偏好 → procedural memory
→ MemoryWritePolicy
   ├─ 判断置信度
   ├─ 判断证据数量
   ├─ 判断是否已有冲突记忆
   └─ 决定 create / merge / reject
→ MemoryRepository
→ EmbeddingService
→ memory_items
```

---

## 7. 记忆检索流程

```text
当前用户请求
→ MemoryRetrievalService
   ├─ 向量召回
   ├─ 类别过滤
   ├─ scope 过滤
   └─ 时间/置信度过滤
→ MemoryConflictResolver
   ├─ 当前明确要求优先
   ├─ 当前旅行上下文优先
   ├─ explicit > semantic > inferred
   ├─ 最近确认 > 旧记录
   └─ 场景隔离
→ Prompt 注入
```

### 初始参数

```text
top_k: 8
inject_top_k: 5
min_relevance: 0.70
semantic_write_threshold: 0.85
procedural_write_threshold: 0.85
min_evidence_count: 2
```

---

## 8. 冲突处理

## 8.1 规则

```text
1. 用户当前明确要求最高
2. 当前旅行上下文高于长期偏好
3. explicit 高于 semantic
4. semantic 高于 episodic
5. 最近确认高于旧记录
6. 场景隔离，不跨场景误用
7. 不用新值简单覆盖旧值，必须保留证据
```

## 8.2 示例

已有语义记忆：

```text
用户喜欢紧凑行程
```

当前用户说：

```text
带孩子，不要太累
```

处理：

```text
短期记忆记录：本次旅行要慢节奏
不覆盖旧语义记忆
推荐时当前需求优先
行程生成 prompt 中明确冲突
```

---

## 9. 程序记忆应用场景

## 9.1 Planner 层

影响：

```text
工具顺序
是否先查预算
是否先查天气
是否先给候选城市
```

示例程序记忆：

```text
trigger = 用户要求规划行程
preferred_sequence = [recommend_destination, estimate_budget, plan_itinerary]
```

Planner 可以据此调整计划，但不能违背用户当前明确指令。

## 9.2 输出层

影响：

```text
输出格式
是否按天展示
是否先列三个候选
是否附引用
```

## 9.3 工具层

影响：

```text
常用交通方式
常用出发城市
地图偏好
火车查询习惯
```

---

## 10. 用户控制

必须提供：

```text
查看 Memory
修改 Memory
删除单条 Memory
清空全部 Memory
关闭个性化
关闭长期记忆
导出 Memory
```

### 状态字段

`users` 表已有：

```text
personalization_enabled
long_term_memory_enabled
```

### 关闭个性化

```text
不再检索和注入长期记忆
已有数据保留，除非用户删除
```

### 关闭长期记忆

```text
不再写入新长期记忆
已有数据保留，除非用户删除
```

---

## 11. 隐私规则

```text
敏感信息默认不保存
健康、过敏、身份证件、财务账号不保存
除非用户明确授权
写入前标明 evidence_type
用户删除用户账号时同步删除：
  memory_items
  memory_evidence
  memory embedding
```

---

## 12. 实施计划

## 12.1 第一批：数据结构和服务

1. `memory_items` 增加 embedding 字段
2. `memory_evidence` 增加 evidence_type、confidence
3. 新增 `MemoryRepository`
4. 新增 `MemoryWritePolicy`
5. 新增 `MemoryRetrievalService`
6. 新增 `MemoryConflictResolver`
7. Alembic migration

## 12.2 第二批：提取和写入

1. 扩展 `ProfileExtraction`
2. 新增 `MemoryCandidate`
3. FeedbackAgent 输出 MemoryCandidate
4. 支持 explicit / semantic / episodic / procedural
5. 证据写入
6. 相同记忆合并

## 12.3 第三批：注入和影响

1. ContextBuilder 注入 semantic memory
2. Planner 使用 procedural memory
3. 推荐排序使用 episodic memory
4. 冲突处理
5. 记忆引用展示

## 12.4 第四批：用户控制

1. Memory CLI
2. Memory API 预留
3. 查看 / 修改 / 删除
4. 关闭个性化
5. 导出
6. 隐私测试

---

## 13. 验收标准

- [ ] 短期记忆不会误写成长期记忆
- [ ] 用户明确说“记住”能写入 explicit memory
- [ ] 多次相同偏好能归纳 semantic memory
- [ ] 用户接受/拒绝能写入 episodic memory
- [ ] 用户流程偏好能写入 procedural memory
- [ ] 单次模糊推断不会写入长期记忆
- [ ] 当前旅行需求优先于长期偏好
- [ ] 不同场景记忆不会互相污染
- [ ] Memory 检索有相关性阈值
- [ ] Prompt 注入有数量和 Token 限制
- [ ] 用户可以查看、修改、删除 Memory
- [ ] 用户可以关闭个性化
- [ ] 删除用户时 Memory 全量删除

---

## 14. 与现有系统的关系

### 当前已有能力

```text
chat_sessions / chat_messages
trips / trip_plan_versions
LangGraph checkpoints
UserProfile
TravelRequest
memory_items
memory_evidence
```

### 本阶段不推翻现有结构

```text
UserProfile 保留为兼容视图
逐步迁移为 semantic memory
TravelRequest 保留为短期记忆的一部分
```

---

# 最终记忆链路

```text
用户输入
→ 短期记忆更新
→ 长期记忆候选提取
→ 写入策略判断
→ 记忆持久化
→ 记忆向量检索
→ 冲突处理
→ 上下文注入
→ Planner / Tool / Ranking 使用
→ 用户查看与控制
```
