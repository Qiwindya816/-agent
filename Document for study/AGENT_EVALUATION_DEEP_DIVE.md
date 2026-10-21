# TravelMind Agent 评测深度解析：数据集、指标、组件评测与端到端方法

> 本文档以当前工作区代码为准，说明 TravelMind 现有评测体系如何实现、每类评测具有什么功能、采用了哪些原理和技术栈、对应项目中的哪些代码，以及如何从现有组件评测演进为真正的端到端 Agent 评测。
>
> 先给结论：当前项目已经具备一套可运行的离线评测骨架，但它主要覆盖 **RAG 检索、结构化行程校验、Memory 冲突消解与隐私隔离、结构化 LLM 输出**。它还不是完整的 Agent 端到端评测平台，因为目前没有统一执行完整对话图并同时判断任务结果、工具轨迹、状态变化、事实依据、成本和延迟。

---

## 1. Agent 评测到底在评什么

普通函数通常是“输入确定，输出也相对确定”；Agent 则不同：它会理解意图、规划步骤、调用工具、读写状态、检索知识、生成自然语言，并可能在失败后重试。因此，Agent 不能只看最终回答是否流畅。

一条完整的 Agent 执行链可以抽象为：

```text
用户输入 + 初始状态
        │
        ▼
意图理解 / 参数抽取
        │
        ▼
任务规划 / 工具选择
        │
        ▼
工具参数 ──► 工具调用 ──► 外部结果
        │                         │
        └──────── 状态更新 ◄─────┘
                         │
                         ▼
                最终回答 / 持久化副作用
```

因此，至少要从五层观察：

| 层级 | 核心问题 | TravelMind 当前覆盖 |
|---|---|---|
| 确定性单元层 | 指标公式、校验器、匹配规则算得对不对 | 已覆盖，主要由 `pytest` 保证 |
| 组件层 | Router、Profile、RAG、Memory、行程校验各自是否正确 | 已覆盖一部分 |
| 轨迹层 | 工具选得对不对、参数对不对、顺序和依赖对不对 | Router 仅覆盖工具计划，尚未统一评真实执行轨迹 |
| 结果层 | 用户任务最终是否完成，回答是否有依据且遵守约束 | 仅有部分代理指标和待人工评分样例 |
| 系统层 | 延迟、成本、稳定性、隐私、安全、线上用户反馈 | 隐私和反馈有初步指标，其余尚未系统化 |

这里最重要的原则是：

> **组件分数用于定位原因，端到端任务成功率用于判断 Agent 是否真正有用。**

只测最终答案，无法知道失败发生在路由、工具、检索还是生成；只测单个组件，又可能出现“每个组件单测都通过，串起来仍然失败”。成熟评测必须同时保留这两个视角。

---

## 2. 当前项目的评测组成

当前代码中有两条主要评测线和一层测试保护：

```text
evaluation/datasets/*.json
        │
        ▼
scripts/manage_evals.py
        ├── RAG 检索评测
        ├── 行程确定性评测
        ├── 用户反馈汇总
        ├── Memory 冲突评测
        └── Memory 跨用户隐私检查
                 │
                 ▼
 outputs/evaluations/baseline.json + baseline.md

tests/model_eval_cases.json
        │
        ▼
tests/run_model_evals.py
        ├── Router 结构化输出
        ├── Profile 结构化抽取
        └── Weather 参数抽取
                 │
                 ▼
 outputs/model_eval_report.json

tests/unit/test_evaluation_metrics.py
tests/unit/test_rag_dataset_builder.py
        │
        └── 保证指标公式和数据集构建逻辑本身没有回归
```

对应入口如下：

| 组成 | 主要功能 | 技术栈 | 核心代码 |
|---|---|---|---|
| 离线评测编排 | 选择评测 section、加载用例、聚合结果、设置门槛 | Python、argparse、JSON | [`scripts/manage_evals.py`](../scripts/manage_evals.py) |
| RAG 评测 | Recall、Precision、nDCG、来源可追踪性 | Python、信息检索指标 | [`evaluation/rag.py`](../evaluation/rag.py)、[`evaluation/metrics.py`](../evaluation/metrics.py) |
| 评测集构建 | 真实语料抽样、银集、候选金集、人工复核 | SQLAlchemy、LLM、JSON、CSV | [`evaluation/dataset_builder.py`](../evaluation/dataset_builder.py)、[`scripts/build_rag_evalsets.py`](../scripts/build_rag_evalsets.py) |
| 行程评测 | 时间冲突、预算超限、路线核验完整度 | Pydantic、确定性规则 | [`evaluation/itinerary.py`](../evaluation/itinerary.py)、[`validators/itinerary_validator.py`](../validators/itinerary_validator.py) |
| Memory 评测 | 冲突优先级、错误选择、跨用户读取隔离 | Pydantic、SQLAlchemy、规则评分 | [`evaluation/memory.py`](../evaluation/memory.py) |
| 模型组件评测 | 真实调用 LLM，检查结构化字段 | DeepSeek/OpenAI-compatible SDK、JSON | [`tests/run_model_evals.py`](../tests/run_model_evals.py) |
| 报告 | 输出机器可读 JSON 和人读 Markdown | JSON、Markdown | [`evaluation/reporting.py`](../evaluation/reporting.py) |
| 评测代码单测 | 防止指标和数据构建器自身算错 | pytest、Fake Object | [`tests/unit/test_evaluation_metrics.py`](../tests/unit/test_evaluation_metrics.py)、[`tests/unit/test_rag_dataset_builder.py`](../tests/unit/test_rag_dataset_builder.py) |

---

## 3. 评测数据集：银集、候选金集和人工金集

### 3.1 为什么评测首先是数据问题

指标只有在参考标准可信时才有意义。若“正确答案”本身错误或覆盖面失衡，分数再精确也没有价值。

当前 RAG 评测采用如下数据生命周期：

```text
真实知识库语料
   │
   ├── 按 owner_user_id / source_id 过滤
   ├── 只保留 active 文档、有 embedding、有 theme 的 chunk
   ├── 每个文档选择较长的代表 chunk
   └── 按 城市 × 主题 分层
           │
           ▼
     确定性平衡抽样
           │
           ▼
LLM 生成自然问题，失败时模板回退
           │
           ├── query 必须包含城市
           ├── 不得泄漏完整标题
           └── evidence 必须是原文连续片段
           │
           ▼
rag_silver.json（程序校验银集）
           │
           ▼
按城市 × 主题再次分层抽样
           │
           ▼
rag_golden_review.csv（人工逐条复核）
           │
           ▼
rag_golden.json（approved 后才是真正金集）
```

### 3.2 语料加载与分层抽样

实现位置：[`evaluation/dataset_builder.py`](../evaluation/dataset_builder.py)

`load_xhs_corpus()` 通过 SQLAlchemy 联查：

- `SocialNote`：城市、平台和社交笔记身份；
- `RagDocument`：文档状态、所有者和来源；
- `RagChunk`：主题、正文和向量状态；
- `RagSource`：来源名、URL 和授权状态；
- `SocialMetricSnapshot`：最新互动量。

每个文档只保留一个较长的代表 chunk，避免同一文档在样本中重复占位。`select_balanced()` 再按“城市 × 主题”分桶，用 `SHA-256(seed + document_id)` 形成稳定次序，因此同一语料和同一 seed 可重复得到相同抽样结果。

涉及的技术与原理：

| 功能 | 原理 | 技术栈 |
|---|---|---|
| 数据过滤 | 只在有效、属于目标用户的真实语料上建集 | SQLAlchemy、关系数据库 |
| 分层抽样 | 防止热门城市或主题淹没长尾类别 | `defaultdict`、确定性排序 |
| 可复现性 | 固定 seed 与文档 ID 哈希，不依赖随机全局状态 | SHA-256 |
| 数据溯源 | 每条 case 保留文档、chunk、来源、互动信息 | JSON provenance 字段 |

注意：`CorpusItem.quality_score` 定义了长度和互动量的综合质量分，但当前 `select_balanced()` 并没有用它排序。也就是说，当前选择强调稳定和平衡，而不是优先选择最高互动内容。

### 3.3 自动生成银集

`generate_annotations()` 支持两种模式：

- `template`：用确定性模板生成问题；
- `llm`：让模型从真实正文生成自然问题和逐字证据。

LLM 生成时使用：

- `temperature=0`，降低随机性；
- 批量 prompt，减少 API 调用次数；
- 只接受允许的 `document_id`；
- 检查问题长度、城市、标题泄漏；
- 检查 `answer_evidence` 是否确实存在于原文；
- 响应异常时回退到模板，保证流程可运行。

`build_silver_payload()` 为每条样本写入精确 `document_id` 相关性规则和 `relevance=3`。银集状态是 `synthetic_validated`，它表示“程序检查通过”，不表示“人类确认正确”。

### 3.4 从银集到人工金集

`build_gold_candidate()` 按城市和主题分层，从银集中选出候选条目；LLM 生成且证据更完整的样本会排在前面。随后 `_write_review_csv()` 生成适合 Excel 打开的 UTF-8 BOM CSV。

人工审核至少要判断：

1. 问题是不是自然用户真的可能提出的；
2. 问题是否只有一个清晰含义；
3. 原文证据是否足以支持问题；
4. 标注的目标文档是否确实相关；
5. 问题是否泄漏了标题或答案；
6. 城市和主题分布是否合理。

`finalize-review` 会把 CSV 中修订后的问题和证据回写到 JSON，剔除 `rejected`，保留 `pending_human_review`，只有所有保留项都通过时才把顶层 `calibration_status` 设置为 `approved`。

实现位置：[`scripts/build_rag_evalsets.py`](../scripts/build_rag_evalsets.py)

### 3.5 数据集校验不是质量审核

`validate_payload()` 会检查：

- case ID 与 query 是否重复；
- query 是否为空；
- 是否恰好有一个精确 `document_id` 规则；
- 目标文档是否仍在当前有效语料中；
- evidence 是否是当前 chunk 的连续原文；
- city 过滤条件与语料是否一致；
- provenance 中的 chunk ID 是否仍一致；
- 已标为 approved 的数据集是否仍存在未审核 case。

这些是**结构正确性和数据新鲜度检查**，并不能替代人工对自然性、歧义和相关性的判断。

---

## 4. RAG 评测

### 4.1 怎么实现

入口：`evaluate_rag_cases(retrieval, cases, default_user_id, k)`

实现位置：[`evaluation/rag.py`](../evaluation/rag.py)

每条 case 的执行过程是：

```text
读取 query / user_id / filters / k
        │
        ▼
retrieval.search(...)
        │
        ▼
前 K 条结果逐条与黄金规则匹配
        │
        ├── 精确字段：chunk_id / document_id / source_name / source_url
        ├── contains_all：正文包含全部词
        └── contains_any：正文至少包含一个词
        │
        ▼
生成每个位置的 graded relevance
        │
        ▼
计算 Recall@K / Precision@K / nDCG@K
        │
        ├── 检查来源字段完整性
        └── 保存逐 case 检索结果与命中详情
```

它采用依赖注入：只要求 `retrieval` 对象提供 `search()`。单元测试可传 `FakeRetrieval`，正式运行则传 [`services/rag_retrieval.py`](../services/rag_retrieval.py) 中的 `RagRetrievalService`。

### 4.2 具有什么功能

#### 功能 A：Recall@K

回答：“金集中应找到的相关项，有多少被前 K 个结果覆盖？”

```text
Recall@K = 前 K 条结果命中的不同黄金规则数 / 黄金规则总数
```

Recall 高表示漏召回少。对回答生成来说，Recall 往往是第一道门槛：所需证据没被检索到，后续模型很难凭空答对。

代码：[`evaluation/metrics.py`](../evaluation/metrics.py) 的 `recall_at_k()`。

#### 功能 B：Precision@K

回答：“前 K 个位置里，有多少结果是相关的？”

```text
Precision@K = 前 K 个位置中 relevance > 0 的数量 / K
```

当前实现即使实际返回少于 K 条，也仍以 K 为分母，因此对短结果列表采取较保守的评分。

代码：[`evaluation/metrics.py`](../evaluation/metrics.py) 的 `precision_at_k()`。

#### 功能 C：nDCG@K

回答：“高相关结果是否排在更靠前的位置？”

```text
DCG@K  = Σ (2^rel_i - 1) / log2(i + 2)
nDCG@K = DCG@K / IdealDCG@K
```

它同时考虑相关性等级和排名折损。`relevance=3` 的结果放在第一名，比放在第五名得分高。

代码：[`evaluation/metrics.py`](../evaluation/metrics.py) 的 `ndcg_at_k()`。

#### 功能 D：来源可追踪性

`source_traceability` 检查前 K 个结果是否同时具有：

- `document_id`；
- `source_name`；
- `source_url`；
- `fetched_at`；
- `source_authorization_status`。

```text
source_traceability = 来源字段完整的结果数 / 实际返回结果数
```

它衡量“能否追到证据来源”，不衡量来源内容本身是否真实。

#### 功能 E：citation_accuracy

当前实现为：

```text
citation_accuracy = 可追踪且命中黄金规则的结果数 / 可追踪结果数
```

这个名字容易产生误解。它更接近“带完整来源结果的相关精确率”，并没有检查最终答案中的某条自然语言 claim 是否被某个 citation 逐句支持。真正的引用忠实度评测还需要做 claim 拆分、claim-to-evidence 对齐和 entailment 判断。

### 4.3 技术栈与原理

| 能力 | 技术栈 | 原理 |
|---|---|---|
| 检索执行 | `RagRetrievalService`、可选 EmbeddingService | 用真实检索链跑金集，而不是只测试静态排序函数 |
| 相关性判断 | 精确 ID、来源字段、关键词规则 | 将人工标准转成可执行 predicate |
| 排名指标 | Python、`math.log2` | 经典信息检索评测 |
| 可审计明细 | dataclass/dict 归一化、JSON | 不只留总分，也保留每条结果 |
| 宏平均 | 各 case 指标等权平均 | 避免样本条目多的 case 独占总分 |

### 4.4 当前边界

- 评的是“检索结果”，不是最终回答的正确性和忠实度；
- 关键词规则可能误把只出现关键词但语义无关的文本判为相关；
- 当前金集每条通常只有一个目标文档，难以完整描述“多个答案都合理”的情况；
- 宏平均没有置信区间，样本很少时分数波动无法体现；
- 没有按城市、主题、问题难度分别输出 slice 指标；
- 没有记录检索延迟、Embedding/Reranker 成本；
- 数据集未 `approved` 时，runner 只发 warning，仍会给出分数。

---

## 5. 行程评测

### 5.1 怎么实现

入口：`evaluate_itineraries(cases)`

实现位置：[`evaluation/itinerary.py`](../evaluation/itinerary.py)

每条 case 先通过 `Itinerary.model_validate()` 转成结构化 Pydantic 模型，再交给 `ItineraryValidator` 做确定性校验。

```text
JSON case
   │
   ▼
Pydantic Itinerary 校验
   │
   ▼
ItineraryValidator
   ├── 时间顺序和重叠
   ├── 路线引用是否合法
   ├── 活动强度
   ├── 费用一致性
   └── POI / 路线核验状态
   │
   ▼
评测层额外计算预算超限和路线覆盖
```

### 5.2 具有什么功能

#### 功能 A：时间冲突率

校验器检查：

- 结束时间是否早于或等于开始时间；
- 当前活动开始时间是否早于前一活动结束时间。

评测器根据错误文本中的“重叠”或“结束时间”判断该 case 是否存在时间冲突，然后统计：

```text
time_conflict_rate = 有时间冲突的行程数 / 行程总数
```

#### 功能 B：预算超限率

当前实现分别求：

- 全部 activity 的 `estimated_cost` 合计；
- 全部 day 的 `estimated_daily_cost` 合计；
- itinerary 的 `total_estimated_cost`。

取三者最大值作为 `calculated_cost`，再与 case 中的 `budget_limit` 比较。这是一种保守策略，可避免模型通过少填某一层费用来规避预算检查。

```text
budget_overrun_rate = calculated_cost > budget_limit 的行程数 / 总行程数
```

#### 功能 C：路线未充分核验率

若一天有 `n` 个活动，至少需要 `n - 1` 段活动间转移。评测器统计同时满足以下条件的 route：

- `verification_status == "verified"`；
- `duration_minutes` 不为空。

如果已核验 route 少于理论转移数，该行程被记为 `route_infeasible=True`。更准确地说，这个指标衡量的是“路线核验覆盖不足”，并未真的计算地理路线是否可达。

#### 功能 D：用户反馈信号

`evaluate_trip_feedback()` 从数据库汇总：

- 行程版本数；
- feedback 总数；
- `modify` 次数；
- `accept`、`reject`、其他反馈的数量；
- 接受率。

```text
acceptance_rate = accept / (accept + reject)
```

`modify` 不进入接受率分母，而是单独报告。它属于线上行为代理指标，不等价于经过实验控制的满意度。

### 5.3 技术栈与原理

| 功能 | 技术栈 | 原理 |
|---|---|---|
| 输入契约 | Pydantic v2 | 先保证结构合法，再计算业务质量 |
| 业务校验 | Python 确定性规则 | 对时间、预算等可计算问题不用 LLM 当裁判 |
| 反馈汇总 | SQLAlchemy `select`、`func.count`、`group_by` | 从真实持久化数据形成线上代理指标 |
| 明细输出 | JSON | 每条 case 保留错误和 warning，便于定位 |

### 5.4 当前边界

- [`evaluation/datasets/itinerary_cases.json`](../evaluation/datasets/itinerary_cases.json) 当前只有 1 条有效基线样例，无法代表复杂行程分布；
- 评测输入是已经写好的结构化 itinerary，并没有调用 Agent 从自然语言生成行程；
- 没有评景点真实性、营业时间、天气适配、路线地理距离和特殊人群适配；
- `route_infeasible` 实际是路线核验数量不足，不是完整的可行性证明；
- 总套件会因时间冲突或预算超限失败，但目前不会因 `route_infeasible_rate > 0` 自动失败；
- 接受率易受用户群、场景难度和反馈选择偏差影响，不能跨版本直接裸比较。

---

## 6. Memory 评测

### 6.1 怎么实现

当前 Memory 评测分为两部分：

1. 用静态 case 评 `MemoryConflictResolver` 的选择结果；
2. 用真实数据库逐条检查 `MemoryRepository` 是否阻止跨用户读取。

实现位置：[`evaluation/memory.py`](../evaluation/memory.py)

### 6.2 具有什么功能

#### 功能 A：冲突消解准确率

每条 case 提供：

- `memories`：候选记忆；
- `scope`：本次使用范围；
- `expected_selected`：必须选中的 memory ID；
- `expected_first`：必须排第一的 memory ID；
- `forbidden_selected`：绝不能选中的 memory ID。

评测器把字典转成 `RetrievedMemory`，调用 `MemoryConflictResolver.resolve()`，再判断：

- 所有预期项是否都被选择；
- 禁止项是否均未选择；
- 第一名是否符合预期。

```text
conflict_resolution_accuracy = 完全通过的冲突 case 数 / 冲突 case 总数
```

当前基线样例验证“显式偏好优先于根据行为推断出的 semantic 偏好”。

数据：[`evaluation/datasets/memory_cases.json`](../evaluation/datasets/memory_cases.json)

#### 功能 B：错误选择率

```text
wrong_retrieval_rate = 被选中的 forbidden memory 数 / 所有被选中 memory 数
```

虽然字段名叫 `wrong_retrieval_rate`，它当前并不是评估数据库或向量检索是否召回正确，而是评估**冲突消解后选择列表中出现禁止项的比例**。若要评 Memory Retrieval，还需要另外构建 query → relevant memory 的金集并计算 Recall@K、MRR 等指标。

#### 功能 C：跨用户隐私检查

`evaluate_memory_privacy()` 会遍历数据库中所有 `MemoryItem`，为每条记忆构造一个 outsider 用户 ID，然后调用：

```text
repository.get_item(outsider_user_id, memory_id)
```

如果外部用户仍拿到该条记忆，就计为一次泄漏。

```text
privacy_pass_rate = (checked_items - leaks) / checked_items
```

这个检查验证 repository 的所有权过滤是否生效，是确定性的越权读取测试。

### 6.3 技术栈与原理

| 功能 | 技术栈 | 原理 |
|---|---|---|
| Case 反序列化 | Pydantic、ISO datetime | 用与生产一致的 schema 评真实 resolver |
| 冲突评测 | 集合包含、排序首项、禁止集合 | 同时检查选择完整性、优先级和负例 |
| 隐私检查 | SQLAlchemy、Repository Pattern | 通过生产查询接口验证对象级访问边界 |
| 明细诊断 | JSON | 保存实际选择和预期选择 |

### 6.4 当前边界

- 静态 Memory 数据集目前只有 1 条冲突样例；
- 没有评候选记忆抽取是否正确；
- 没有评 pending → active 的晋升、合并、过期和删除流程；
- 没有评 query 相关性、跨轮记忆是否在正确时机被召回；
- 隐私检查只覆盖 `get_item()` 这一条读取路径，不能证明搜索、列表、导出、日志等全部入口都无泄漏；
- 数据库为空时隐私通过率为 1.0，runner 会给 warning；这代表“没有发现泄漏”，不代表已有足够证据证明安全；
- 总套件目前只把 `privacy_leak_count > 0` 设为失败门槛，没有把冲突准确率接入 gate。

---

## 7. 结构化 LLM 组件评测

### 7.1 怎么实现

入口：[`tests/run_model_evals.py`](../tests/run_model_evals.py)

数据：[`tests/model_eval_cases.json`](../tests/model_eval_cases.json)

runner 会实际创建 `LLMService` 并调用当前配置的 DeepSeek 模型。自动执行的组件有：

- `router`：意图识别、工具选择、多步骤计划；
- `profile`：用户画像与旅行约束抽取；
- `weather`：地点和预报天数抽取。

每次调用固定 `temperature=0`，然后用 `_score_case()` 检查：

- `expected`：字段精确相等；
- `expected_contains`：列表包含所有期望元素；
- `expected_empty`：字段必须是 `None`、空字符串或空列表。

Router 若返回 `steps`，runner 会把第一步字段摊平，并额外生成 `tool_names`，因此既能测第一工具，也能测多步骤是否包含所需工具。

### 7.2 覆盖了哪些能力

| 组件 | 评测能力 | 代表性风险 |
|---|---|---|
| Router | 单意图路由、多意图计划、依赖已有行程、提示注入 | 选错工具、遗漏第二任务、被用户文本中的伪指令劫持 |
| Profile | 中英文抽取、金额单位、日期、兴趣、饮食、行动限制、负向偏好 | 无依据补全、字段遗漏、归一化错误 |
| Weather | 中英文地点、别称、天数上限、缺失地点、提示注入 | 猜测地点、超出 provider 上限、格式失控 |

运行说明：[`tests/MODEL_EVAL_GUIDE.md`](../tests/MODEL_EVAL_GUIDE.md)

### 7.3 自动评测与人工样例的区别

`model_eval_cases.json` 还定义了 `component="manual"` 的生成质量样例，包括：

- 目的地推荐约束遵循；
- 老人和儿童同行的行程质量；
- 只修改指定日期的信息保持；
- 预算数学一致性；
- 不可能需求的处理；
- 虚构地点的幻觉控制。

但 `STRUCTURED_COMPONENTS` 只包含 `router/profile/weather`，因此当前 runner 会过滤掉 `manual` 样例。它们目前是人工检查清单，而不是已经执行并产出分数的自动评测。

### 7.4 技术栈与原理

| 功能 | 技术栈 | 原理 |
|---|---|---|
| 模型调用 | OpenAI-compatible client、DeepSeek | 评当前真实模型和 Prompt 组合 |
| 结构化输出 | JSON、项目 Prompt Builder | 把自由文本问题转为可断言字段 |
| 确定性评分 | Python exact/contains/empty 判断 | 能规则判断的结果不用另一个 LLM 主观裁决 |
| 分组件报告 | JSON | 同时输出总通过率和组件通过率 |

### 7.5 当前边界

- 只测模型输出，不执行完整 LangGraph 和真实工具；
- 只做一次调用，没有重复运行后的稳定率；
- 没有记录 token、费用、首 token 延迟和总延迟；
- exact match 对同义表达、顺序差异可能过严；contains 对额外错误项又可能过松；
- 异常统一计为失败，但没有把 API 故障、格式错误和语义错误分开统计；
- `temperature=0` 能降低随机性，但不能保证云模型完全确定；
- 没有固定模型版本快照时，供应商更新可能让同一代码产生新结果；
- manual 样例尚未接入人评或 LLM-as-a-judge 流程。

---

## 8. 总评测编排、门槛与报告

### 8.1 怎么实现

[`scripts/manage_evals.py`](../scripts/manage_evals.py) 负责：

1. 解析 `--sections`、`--k`、`--min-rag-recall` 等参数；
2. 从 JSON 加载各类 cases 和 metadata；
3. 初始化数据库和检索服务；
4. 分别运行 RAG、行程和 Memory 评测；
5. 汇总 warnings、failures 和全局 status；
6. 调用 `write_reports()` 输出 JSON 与 Markdown。

### 8.2 当前硬门槛

当前总状态变为 `fail` 的条件只有：

```text
RAG Recall@K < --min-rag-recall（默认 0.6）
或 行程 time_conflict_rate > 0
或 行程 budget_overrun_rate > 0
或 Memory privacy_leak_count > 0
```

以下指标虽然会报告，但目前不会让 suite 自动失败：

- RAG Precision@K、nDCG@K；
- citation_accuracy、source_traceability；
- route_infeasible_rate；
- Memory wrong_retrieval_rate、conflict_resolution_accuracy；
- 用户接受率和修改次数；
- 结构化 LLM 评测通过率，因为它是另一套 runner。

因此必须区分：

> `status=pass` 表示“通过了当前接入的少数门槛”，不是“Agent 全能力合格”。

### 8.3 报告格式

[`evaluation/reporting.py`](../evaluation/reporting.py) 输出：

- `baseline.json`：机器读取、适合做版本对比和 CI gate；
- `baseline.md`：只摘录各 section 的宏观指标，方便人读。

JSON 报告保留逐 case 结果，排查回归时应优先看它。Markdown 目前是摘要报告，不包含完整失败样例和版本差异。

### 8.4 为什么评测代码也需要测试

评测器一旦算错，会出现“模型没变但分数变了”或“坏版本被错误放行”。当前：

- [`tests/unit/test_evaluation_metrics.py`](../tests/unit/test_evaluation_metrics.py) 验证 IR 指标、RAG 来源字段和行程错误检测；
- [`tests/unit/test_rag_dataset_builder.py`](../tests/unit/test_rag_dataset_builder.py) 验证分层数量、case ID 唯一、LLM 失败回退、候选金集待人工审核状态。

测试使用 `FakeRetrieval` 隔离真实数据库与网络，这属于 test double / dependency injection。它让指标层测试快速、稳定、可在 CI 中重复运行。

---

## 9. 如何运行当前评测

### 9.1 运行确定性单元测试

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_evaluation_metrics.py `
  tests\unit\test_rag_dataset_builder.py -q
```

这一步不应调用外部 LLM，适合每次改动都运行。

### 9.2 运行离线业务评测

```powershell
# 全部 section，不调用 Embedding 服务
.\.venv\Scripts\python.exe -m scripts.manage_evals --no-embedding

# 完整 RAG，包括配置好的 Embedding 服务
.\.venv\Scripts\python.exe -m scripts.manage_evals

# 单独运行
.\.venv\Scripts\python.exe -m scripts.manage_evals --sections rag --no-embedding
.\.venv\Scripts\python.exe -m scripts.manage_evals --sections itinerary
.\.venv\Scripts\python.exe -m scripts.manage_evals --sections memory
```

默认报告：

```text
outputs/evaluations/baseline.json
outputs/evaluations/baseline.md
```

运行前要注意：

- 该套件会读取当前 `DATABASE_URL`；
- RAG 和 Memory 隐私评测依赖数据库中的真实数据；
- 不带 `--no-embedding` 时需要有效的 DashScope Embedding 配置；
- 金集未批准或数据库数据为空时应认真处理 warning；
- runner 的设计目标是只读业务数据并写报告。

### 9.3 运行真实模型组件评测

```powershell
# 少量冒烟，实际产生 API 调用
.\.venv\Scripts\python.exe tests\run_model_evals.py --limit 3

# 按组件
.\.venv\Scripts\python.exe tests\run_model_evals.py --component router
.\.venv\Scripts\python.exe tests\run_model_evals.py --component profile
.\.venv\Scripts\python.exe tests\run_model_evals.py --component weather

# 全部自动结构化样例
.\.venv\Scripts\python.exe tests\run_model_evals.py
```

需要有效的 `DEEPSEEK_API_KEY`，默认报告写入 `outputs/model_eval_report.json`。

### 9.4 构建和维护 RAG 评测集

```powershell
# 查看城市 × 主题覆盖
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets coverage --source-id <source_id>

# 建立银集、候选金集和人工复核表
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets build `
  --source-id <source_id> `
  --query-mode llm `
  --silver-per-cell 6 `
  --gold-per-cell 2

# 语料更新后检查金集是否仍有效
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets validate `
  --source-id <source_id> `
  --dataset evaluation\datasets\rag_golden.json

# 将人工复核 CSV 回写金集
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets finalize-review `
  --source-id <source_id>
```

---

## 10. 真正的 Agent 端到端评测应该怎么设计

当前项目最值得补的一层，是对完整 `TravelGraph` 执行进行评测。一个端到端 case 不应只保存期望文本，而应保存初始状态、允许或禁止的轨迹、预期状态变化和结果标准。

### 10.1 建议的 case 结构

```json
{
  "id": "E2E-PLAN-BUDGET-001",
  "category": "multi_intent",
  "input": "给我做大阪五日行程，并把总预算控制在一万元以内",
  "initial_state": {
    "user_profile": {"departure_city": "上海"},
    "current_itinerary": null
  },
  "expected": {
    "required_tools": ["plan_itinerary", "estimate_budget"],
    "forbidden_tools": ["finalize_plan"],
    "tool_dependencies": [["plan_itinerary", "estimate_budget"]],
    "state_assertions": {
      "structured_itinerary.destination": "大阪",
      "structured_itinerary.travel_days": 5
    },
    "result_assertions": {
      "currency": "CNY",
      "max_budget": 10000,
      "must_mention": ["预算"]
    }
  }
}
```

真实 runner 应创建隔离用户与会话，在可控的 fake/provider 环境中执行完整图，然后收集：

- 最终回复；
- `node_trace`；
- `route_plan`；
- 每次工具名、参数、结果和错误；
- 执行前后 AgentState 差异；
- 数据库副作用；
- token、费用和延迟。

### 10.2 结果评测

结果层建议包含：

| 指标 | 判断内容 | 推荐评分方式 |
|---|---|---|
| task_success | 用户目标是否完成 | 确定性断言优先，必要时人评 |
| constraint_satisfaction | 天数、预算、节奏、饮食等是否遵守 | schema + 规则校验 |
| factuality | 景点、价格、天气等事实是否可靠 | 对照工具返回或已批准证据 |
| groundedness | 回答中的 claim 是否由 RAG/工具结果支持 | claim-evidence 对齐，可辅以 judge |
| completeness | 多意图是否全部完成 | 子任务 checklist |
| response_quality | 是否清晰、可执行、不过度冗长 | 有 rubric 的人评或校准 judge |

### 10.3 轨迹评测

轨迹不是要求模型严格走唯一序列，而是判断它是否满足约束：

- required tool 是否至少调用一次；
- forbidden tool 是否未调用；
- 工具参数是否正确、完整且没有凭空补值；
- 有数据依赖的调用顺序是否正确；
- 是否出现无意义重复调用或循环；
- 工具失败后是否采用允许的恢复策略；
- 是否把不可信工具输出当成系统指令执行。

对有多种合法路径的任务，应使用“允许集合 + 部分顺序约束”，而不是把唯一黄金轨迹硬编码为完全相等。

### 10.4 状态与副作用评测

Agent 的正确性还包括“改了该改的，没改不该改的”：

- 用户画像只写入有证据的字段；
- 旅行级偏好不错误写成全局长期偏好；
- 修改第三天时，其他天核心安排保持不变；
- `finalize_plan` 才产生正式版本或导出；
- 跨用户数据始终隔离；
- 失败事务不留下半写入状态；
- 重试不会重复扣款、重复创建版本或重复写 Memory。

这类评测通常通过执行前后的数据库 snapshot/diff 完成。

### 10.5 稳定性、成本和延迟

对非确定模型，同一个 case 至少可以重复 N 次，报告：

```text
pass@1        一次运行成功率
pass^N        N 次全部成功的比例，衡量稳定性
majority_pass N 次中多数成功的比例
```

同时记录：

- 端到端 p50 / p95 latency；
- LLM 输入、输出 token；
- 每个成功任务的平均成本；
- 工具调用次数；
- 超时率、重试率、provider error rate。

性能指标必须和质量一起看。降低延迟但让任务成功率显著下降，不是有效优化。

### 10.6 安全与对抗评测

TravelMind 至少需要这些安全 slice：

- 用户 prompt injection；
- RAG 文档中的间接 prompt injection；
- 工具返回中的恶意指令；
- 跨用户 Memory/RAG/Trip 访问；
- 未授权来源内容的引用与导出；
- 敏感信息写入长期记忆；
- 虚构地点、不可实现行程和极端天气下的诚实拒绝或澄清；
- 超预算、危险路线、特殊人群限制的风险提示。

安全指标应设置为硬 gate，不能用其他普通质量分抵消一次严重泄漏。

---

## 11. 自动评分、人评与 LLM-as-a-Judge 怎么分工

### 11.1 优先级原则

建议按以下顺序选择评分器：

```text
确定性代码断言
    > 外部事实或工具结果对照
    > 人工 rubric 评分
    > 经过人工校准的 LLM-as-a-Judge
```

能用程序直接判断的内容，不应交给 LLM：

- JSON 字段；
- 工具名和参数；
- 时间是否重叠；
- 预算加总；
- 数据库是否多写或越权；
- 引用 ID 是否存在。

更适合人评或 judge 的内容包括：

- 行程是否自然、节奏是否舒适；
- 推荐理由是否充分；
- 回答是否抓住用户真正目标；
- 多种合理方案中哪一个更好。

### 11.2 LLM-as-a-Judge 的正确用法

若引入 judge，应做到：

1. 给出明确 rubric，而不是只问“好不好”；
2. 各维度独立打分，并要求引用被评内容中的证据；
3. 隐藏候选版本身份，避免位置和品牌偏差；
4. 随机交换 A/B 顺序；
5. 用一批人工双标样本计算 judge 与人类的一致性；
6. 对严重安全项保留确定性规则或人工复核；
7. 固定 judge 模型版本、Prompt 和参数；
8. 保存原始 judge 输出，以便审计。

Judge 也是模型，也会漂移、偏好长答案或被被评文本注入。它只能扩展人评，不能天然成为真理来源。

### 11.3 人工 rubric 示例

每个维度用 0～2 分比单一“通过/失败”更容易校准：

| 维度 | 0 分 | 1 分 | 2 分 |
|---|---|---|---|
| 约束遵循 | 违反关键约束 | 遵守主要约束但有遗漏 | 全部关键约束满足 |
| 可执行性 | 明显不可执行 | 基本可行但需用户补充 | 时间、路线和前提清晰 |
| 事实可靠 | 有编造或误导 | 有未核实细节并作提示 | 关键事实有来源或明确不确定性 |
| 完整性 | 遗漏主要子任务 | 完成大部分 | 所有子任务闭环 |
| 表达质量 | 难以理解 | 可读但组织一般 | 清晰、简洁、重点突出 |

正式标注时至少应给标注员正例、反例和边界例，并抽取一部分做双人标注，计算一致性后再讨论分歧。

---

## 12. 评测集应该怎样组织

### 12.1 按能力切片

建议为 TravelMind 建立以下目录或 metadata slice：

```text
basic_single_intent
multi_intent
missing_information
stateful_follow_up
itinerary_refinement
memory_write_and_recall
rag_grounding
tool_failure_recovery
prompt_injection
privacy_isolation
impossible_request
long_context
```

总分只能说明总体趋势，slice 才能告诉你“坏在哪里”。例如总通过率相同的两个版本，一个可能主要坏在长上下文，另一个可能坏在隐私边界，它们的发布风险完全不同。

### 12.2 按数据来源分层

- **手写核心集**：小而精，覆盖关键业务合同；
- **生产回放集**：对线上日志脱敏后抽样，覆盖真实表达；
- **合成扩展集**：扩充别称、语言、边界和对抗变体；
- **失败回归集**：每次线上事故或重要 bug 固化为永久 case；
- **隐藏保留集**：不用于日常 Prompt 调参，防止过拟合。

### 12.3 防止数据泄漏

若开发者能不断看到全部金集并针对它改 Prompt，就会出现“评测集分数升高但真实泛化不变”。建议：

- development set 用于调试；
- validation set 用于版本选择；
- hidden test set 只在发布候选时运行；
- 对合成问题保留来源和生成版本；
- 检查训练/Prompt 示例与测试 case 的近重复；
- 定期轮换生产回放样本。

---

## 13. 指标设计与统计解释

### 13.1 不要只看平均分

建议每次报告至少包含：

- 样本数 `n`；
- 总体指标；
- 分 slice 指标；
- 相对上一基线的变化；
- 逐 case 新增失败和修复列表；
- 对比例指标给置信区间；
- 质量、延迟、成本一起展示。

样本只有 1 条时，0% 和 100% 都只是一个个案。当前 itinerary 和 memory 静态基线都处于这种状态，适合做冒烟检查，不适合据此声称整体能力已被验证。

### 13.2 成对比较优于裸分数比较

比较版本 A/B 时，应让两版运行同一批 cases，再观察每条 case 的变化：

```text
win：A 失败，B 成功
loss：A 成功，B 失败
tie：两者相同
```

成对结果比两个独立平均数更容易识别真实回归。对自然语言质量的人评，也应盲化版本信息并随机候选顺序。

### 13.3 门槛要分级

推荐使用三类 gate：

| 类型 | 示例 | 策略 |
|---|---|---|
| 零容忍安全门槛 | 隐私泄漏、未授权副作用 | 任一失败即阻止发布 |
| 核心能力门槛 | task success、关键工具参数正确率 | 不得低于绝对值，也不得显著回归 |
| 优化指标 | nDCG、表达质量、p95 延迟、成本 | 综合比较，可做权衡但需记录 |

不要把所有指标加权成一个总分后掩盖严重问题。例如一次跨用户泄漏绝不能被更高的回答流畅度抵消。

---

## 14. 失败分析：分数下降后怎么查

建议每条失败自动归入一项主因：

```text
understanding_error       意图或约束理解错误
planning_error            步骤遗漏、依赖顺序错误
tool_selection_error      选错或漏选工具
argument_error            工具参数错误或无依据补全
tool_execution_error      provider、超时或代码异常
retrieval_error           所需证据未召回或排序太后
grounding_error           有证据但回答没有正确使用
state_error               状态未保存、污染或错误覆盖
memory_error              记错、漏记、错召回、冲突错误
validation_error          结构、预算、时间或路线不合法
safety_error              注入、越权、敏感信息、未授权操作
presentation_error        内容正确但表达影响使用
```

排查顺序建议：

1. 先看是否为基础设施或 API 错误；
2. 再看 Router 计划和工具参数；
3. 检查工具实际返回；
4. 检查状态更新和上下文拼装；
5. 检查最终回答是否遗漏已有证据；
6. 最后才判断是否需要改 Prompt 或模型。

“回答不好”不一定是 Prompt 问题。若根因是检索没找到、工具返回错误、上下文被截断或状态被覆盖，只改 Prompt 通常会掩盖而不是解决问题。

---

## 15. 推荐的评测工作流

### 15.1 开发时

```text
改代码 / Prompt
   │
   ▼
运行 pytest 确定性测试
   │
   ▼
运行受影响组件的小评测集
   │
   ▼
检查逐 case diff，而不只看均分
```

### 15.2 合并前

```text
全量离线组件评测
   +
完整 Agent E2E 回归集
   +
安全零容忍集
   +
成本/延迟预算检查
```

### 15.3 发布后

线上只观察匿名聚合指标和经授权的脱敏样本：

- task completion / abandon rate；
- accept / reject / modify；
- 工具错误和重试；
- 延迟和成本；
- 用户主动纠正率；
- Memory 删除、纠正和隐私投诉；
- RAG 无结果率和引用点击/追溯率。

发现高价值失败后，应经过隐私处理和人工确认，再加入离线失败回归集，形成闭环：

```text
线上失败 → 脱敏归因 → 新增回归 case → 修复 → 离线验证 → 发布
```

---

## 16. 针对当前项目的演进路线

### 第一阶段：把现有评测做扎实

1. 将 itinerary 和 memory 静态 case 从 1 条扩展到至少覆盖主要正反例；
2. 为所有 metrics 增加边界测试：空结果、少于 K 条、多个相关项、重复匹配；
3. 把 route、Memory 冲突和来源可追踪性接入明确 gate；
4. 报告中增加 dataset version、代码 commit、模型名和 provider 配置指纹；
5. 分城市、主题和难度输出 slice；
6. 明确区分 API error、schema error 和 semantic failure。

### 第二阶段：建立完整 Agent runner

1. 从自然语言输入执行完整 LangGraph；
2. 用 fake provider 保证基础回归稳定；
3. 捕获真实工具轨迹、节点轨迹和 state diff；
4. 对工具、参数、顺序、最终状态分别断言；
5. 在临时数据库中验证副作用和跨用户隔离；
6. 加入失败注入：天气超时、RAG 空结果、LLM 非法 JSON、数据库重试。

### 第三阶段：补生成质量和事实性

1. 把 `manual` cases 接入结构化人评 rubric；
2. 用人工标注集校准 LLM judge；
3. 增加 claim → evidence 的 groundedness 检查；
4. 用真实 provider 结果验证天气、汇率、路线和 POI；
5. 建立版本 A/B 盲评与成对统计。

### 第四阶段：接入持续评测

1. PR 上跑快速确定性和小型核心集；
2. 定时跑真实模型与 provider 全集；
3. 保存历史报告并展示趋势；
4. 设置安全、质量、延迟和成本门槛；
5. 将线上高价值失败持续补入回归集。

---

## 17. 建议的代码阅读顺序

如果以学习为目的，建议按以下顺序：

1. [`evaluation/datasets/itinerary_cases.json`](../evaluation/datasets/itinerary_cases.json)：先看 case 长什么样；
2. [`evaluation/metrics.py`](../evaluation/metrics.py)：理解 Precision、Recall、nDCG；
3. [`evaluation/rag.py`](../evaluation/rag.py)：看如何从检索结果形成逐 case 指标；
4. [`tests/unit/test_evaluation_metrics.py`](../tests/unit/test_evaluation_metrics.py)：看怎样用 fake 验证评测器；
5. [`evaluation/dataset_builder.py`](../evaluation/dataset_builder.py)：理解银集、金集和分层抽样；
6. [`scripts/build_rag_evalsets.py`](../scripts/build_rag_evalsets.py)：理解标注工作流；
7. [`evaluation/itinerary.py`](../evaluation/itinerary.py) 与 [`validators/itinerary_validator.py`](../validators/itinerary_validator.py)：理解确定性业务规则；
8. [`evaluation/memory.py`](../evaluation/memory.py)：理解状态/隐私评测；
9. [`scripts/manage_evals.py`](../scripts/manage_evals.py)：理解门槛、汇总和报告；
10. [`tests/model_eval_cases.json`](../tests/model_eval_cases.json) 与 [`tests/run_model_evals.py`](../tests/run_model_evals.py)：理解真实 LLM 组件评测；
11. 最后结合 Agent 图、Memory 和 Context 专题，设计完整 E2E case。

---

## 18. 一张表总结“功能—技术—代码—边界”

| 评测部分 | 怎么实现 | 核心功能 | 技术栈/原理 | 对应代码 | 主要边界 |
|---|---|---|---|---|---|
| RAG | 真实检索结果与黄金规则匹配 | 召回、精确率、排序、来源完整性 | IR 指标、规则匹配、宏平均 | `evaluation/rag.py`、`metrics.py` | 未评最终回答忠实度 |
| RAG 数据集 | 真实语料分层抽样，LLM/模板生成，人工审核 | 银集、候选金集、证据校验 | SQLAlchemy、SHA-256、LLM、JSON/CSV | `dataset_builder.py`、`build_rag_evalsets.py` | 自动校验不等于人工金标 |
| 行程 | Pydantic 解析后执行确定性校验 | 时间、预算、路线核验 | Schema、业务规则 | `itinerary.py`、`itinerary_validator.py` | 当前不执行自然语言到行程的完整 Agent |
| 用户反馈 | SQL 聚合已持久化反馈 | 接受率、修改次数、版本数 | SQLAlchemy 聚合 | `evaluation/itinerary.py` | 观察性指标，有选择偏差 |
| Memory | 静态候选经 resolver 后与期望集合比较 | 冲突优先级、禁止项 | Pydantic、集合断言 | `evaluation/memory.py` | 不等于 Memory 检索质量 |
| Memory 隐私 | outsider 用户读取每条 Memory | 对象级跨用户隔离 | Repository、SQLAlchemy | `evaluation/memory.py` | 只覆盖一条读取路径 |
| LLM 组件 | 实际调用模型并检查 JSON 字段 | Router/Profile/Weather | DeepSeek、temperature 0、exact/contains | `tests/run_model_evals.py` | 不执行完整图，manual 未自动化 |
| 编排与门槛 | 聚合 section，比较阈值，写报告 | 基线、warning、pass/fail | argparse、JSON、Markdown | `scripts/manage_evals.py`、`reporting.py` | 当前 gate 覆盖不完整 |
| 评测器测试 | fake 输入验证指标和构建器 | 防止评测代码回归 | pytest、dependency injection | `tests/unit/test_evaluation_metrics.py` 等 | 不能替代真实模型和真实数据评测 |

---

## 19. 核心学习结论

1. **先定义成功，再写评测。** Agent 的“好”必须拆成任务结果、轨迹、状态、安全、成本和体验。
2. **确定性问题用确定性代码。** 时间、预算、字段、工具和权限都不该优先交给 LLM judge。
3. **金集质量比指标复杂度更重要。** 银集适合扩量，正式结论必须依赖人工校准的数据。
4. **端到端与组件评测缺一不可。** 前者回答“能不能完成任务”，后者回答“为什么失败”。
5. **总分不能掩盖严重风险。** 隐私泄漏、越权副作用和安全问题必须是独立硬门槛。
6. **每次失败都应沉淀为回归 case。** 评测集应该随着真实系统问题持续成长。
7. **报告必须可审计。** 除宏观指标外，还要保留 case、轨迹、实际输出、模型/数据版本和失败原因。
8. **评测本身也是软件。** 指标、数据构建、judge 和报告都要被测试、版本化和审查。

当前 TravelMind 已经有一个不错的起点：真实语料金银集、经典检索指标、确定性业务校验、Memory 隐私检查和真实模型结构化样例都已具备。下一步最有价值的工作，不是继续堆更多孤立分数，而是建立一个能够执行完整 Agent 图、捕获轨迹与状态差异、同时评任务成功和安全边界的统一 E2E runner。
