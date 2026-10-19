# TravelMind RAG 深度解析：从文档到生成上下文

> 本文档汇总项目内所有 RAG 相关实现的完整知识链：数据分块、向量存储、多路召回、RRF 融合、可选 Rerank 精排、用户隔离、与 Agent 衔接。
> 所有代码引用均以当前工作区为准；本文会帮助你一次性把 RAG 全链路弄明白。

---

## 1. 整体架构：一张图看懂 RAG 流程

```text
【离线入库】                              【在线检索】

原始资料（官方说明 / 攻略 / 模板 / 小红书笔记）
    │
    ▼
RagSource（来源登记：授权状态、URL、所有者）
    │
    ▼
RagDocument（文档去重、原始归档、发布时间）
    │
    ▼
RagChunker 切块（fact / guide / template 三种规则）
    │
    ▼
RagChunk 落库
  ├── chunk_text（文本）
  ├── embedding（向量，pgvector vector(1024)）
  ├── tsv（全文搜索 tsvector，PostgreSQL 生成列）
  └── city / theme / travel_days / audience / poi_id
  └── owner_user_id（权限隔离）
    │
    ▼
                                        用户发起请求
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              │                             │                             │
              ▼                             ▼                             ▼
        多路召回（4种）              RRF 融合                    加载完整元数据
  ├ dense：pgvector 余弦相似度   ├ score += 1/(60+rank_i)        ├ source_name
  ├ bm25：PG 全文 + ILIKE 兜底   ├ 按融合分数降序排列             ├ source_url
  ├ geo：经纬度欧氏距离          └ final_k = rag_rrf_top_k        ├ published_at
  └ template：city/theme/days                                  └ likes/collects
              │                             │
              └─────────────────────────────┼─────────────────────────────┘
                                            │
                                            ▼
                            可选 Rerank 精排（默认关闭）
                         query 与候选 chunk 联合相关性打分
                                             │
                                             ▼
                                RagRetrievalService.search()
                                            │
                                            ▼
                            ToolExecutor（plan_itinerary 等）
                                            │
                                            ▼
                            ContextBuilder.build()
                                            │
                                            ▼
                            工具 prompt 中出现「检索到的参考知识」

---

## 2. 数据存储结构：Source → Document → Chunk 三层模型

### 2.1 三层表关系

```text
rag_sources（来源）
  ├── 唯一标识：source_id
  ├── 核心字段：source_type、name、url、authorization_status、owner_user_id
  └── 含义：资料来自谁、是否可检索

rag_documents（文档）
  ├── 唯一标识：document_id
  ├── 外键：source_id → rag_sources.source_id
  ├── 核心字段：content_hash、raw_file_path、title、status、owner_user_id
  └── 含义：一篇具体文档，哈希防重，归档原文

rag_chunks（切片）
  ├── 唯一标识：chunk_id
  ├── 外键：document_id → rag_documents.document_id
  ├── 核心字段：chunk_text、chunk_type、embedding、tsv
  ├── 扩展维度：city/district/poi_id/latitude/longitude/theme/travel_days/audience
  └── 含义：真正参与检索和评分的小文本块
```

`db/models.py` 中定义的核心字段：

| 字段 | 类型 | 作用 |
|------|------|------|
| `embedding` | `Vector(1024)` (PG) / `JSON` (SQLite) | 向量化表示，用于 dense 召回 |
| `tsv` | `tsvector` (PG生成列) / `Text` (SQLite) | 全文搜索索引，用于 BM25/文本召回 |
| `owner_user_id` | `String`（可空） | `NULL` = 公共数据；非空 = 私有数据 |
| `city` | `String` | 按城市过滤 |
| `theme` | `String` | 按旅游主题过滤 |
| `travel_days` | `Integer` | 按行程天数过滤 |
| `audience` | `String` | 按人群过滤 |
| `poi_id` | `String` | POI 精确关联 |
| `latitude`/`longitude` | `Float` | 地理距离召回 |

---

### 2.2 数据流向图

```text
用户上传文档 / 小红书采集
       │
       ▼
RagIngestionService.create_source()
       │
       ▼
RagIngestionService.ingest_document()
       │
       ├── 1. 计算 content_hash，检查是否重复
       │      SELECT … WHERE source_id = ? AND content_hash = ?
       │
       ├── 2. 保存原文到本地磁盘 rag_data/{source_id}/{title}.txt
       │
       ├── 3. 创建 RagDocument 记录
       │
       ├── 4. RagChunker.chunk() 按类型切块
       │       └─ fact → _chunk_facts()     （按段落）
       │       └─ guide → _chunk_guide()    （按 Markdown 标题）
       │       └─ template → _chunk_template()（按 Day 标记）
       │
       ├── 5. EmbeddingService.embed_texts() 调用向量模型
       │       └─ OpenAI 兼容 API（默认 DashScope text-embedding-v3）
       │
       ├── 6. 每个 RagChunk 逐行写入数据库
       │       chunk_id, document_id, owner_user_id, chunk_text, chunk_type,
       │       city, theme, travel_days, audience, poi_id,
       │       latitude, longitude, metadata_json, embedding
       │
       └── 7. 更新 RagIngestionJob 状态 = completed / skipped

---

## 3. 数据分块：RagChunker 的三种规则

文件：`services/rag_chunker.py`

### 3.1 为什么需要分块？

原始文档（一篇完整的攻略或长文）直接放入检索会有两个问题：

1. **召回精度差** — 问题可能只涉及文档中的某一节，但整篇文档都返回，增加噪声；
2. **上下文爆炸** — 每次召回几百字的 chunk 比每次返回整篇文档更适合 LLM 的上下文窗口。

分块的目标是：**每个 chunk 都自包含一个完整语义单元**，既能独立被检索命中，进入生成时也有足够的上下文。

### 3.2 三种分块策略

#### 策略一：fact（事实型文档）

```python
def _chunk_facts(self, content, metadata):
    paragraphs = self._paragraphs(content)   # 按空行分段
    return [RagChunkInput(text, "fact", {...metadata, "heading": heading})
            for heading, text in self._with_headings(paragraphs)]
```

工作方式：

- 按 `\n\s*\n`（空行）把文本切成段落；
- 记录每个段落前面最近的一个 Markdown 标题（`# 故宫` 等）；
- 每个段落成为一个独立 chunk，但 metadata 里带着它的所属标题。

举例：故宫开放信息文档

```text
# 故宫

周一闭馆。

需要提前预约。

门票价格旺季 60 元。
```

切成 3 个 chunk：

```text
chunk_1: text="周一闭馆。", heading="故宫"
chunk_2: text="需要提前预约。", heading="故宫"
chunk_3: text="门票价格旺季 60 元。", heading="故宫"
```

每个 chunk 还可以额外带上 `poi_id`、`city` 等元数据，所以后续检索能精确按 POI 或城市过滤。

#### 策略二：guide（攻略型文档）

```python
def _chunk_guide(self, content, metadata):
    for line in content.splitlines():
        if line.startswith("#"):
            ...   # 记录当前标题，切割 chunk
            buffer = []
```

工作方式：

- 每遇到一个 Markdown 标题（`#`、`##` 等）就开始新 chunk；
- 同一标题下的所有行组成一个 chunk；
- `chunk_type = "guide"`；
- 保留标题到 metadata。

举例：

```text
# 交通
住在地铁站附近。

# 餐饮
推荐本地老店。

# 行程
Day 1 上午故宫。
```

切成 3 个 chunk：`交通 / 餐饮 / 行程` 各一个，每个 chunk 自带 `heading` 元数据。

#### 策略三：template（行程模板文档）

```python
def _chunk_template(self, content, metadata):
    for line in content.splitlines():
        match = re.match(r"\s*(?:#|\*\*)?\s*Day\s*(\d+)", line, re.IGNORECASE)
        if match:
            ...   # 按 Day 标记切割
```

工作方式：

- 每遇到 `Day N` 标记开始新 chunk；
- 从 Day 1 到 Day 2 之间的所有内容组成一个 chunk；
- `chunk_type = "template"`；
- 保留 day 编号到 metadata。

举例：

```text
Day 1
上午故宫，下午景山。

Day 2
上午国博，下午王府井。
```

切成 2 个 chunk：Day 1 一个、Day 2 一个。

---

### 3.3 分块的实际例子

测试代码（`tests/unit/test_rag_ingestion.py`）验证了上述行为：

```python
# fact：按段落
chunks = RagChunker().chunk(
    "# 故宫\n\n周一闭馆。\n\n需要提前预约。",
    "fact", {"city": "北京", "poi_id": "B000A8UIN8"})
assert len(chunks) == 2           # 周一闭馆 + 需要提前预约

# guide：按 Markdown 标题
chunks = RagChunker().chunk(
    "# 交通\n住在地铁站附近。\n\n# 餐饮\n推荐本地老店。",
    "guide", {"city": "成都"})
assert len(chunks) == 2           # 交通 + 餐饮

# template：按 Day
chunks = RagChunker().chunk(
    "Day 1\n上午故宫，下午景山。\nDay 2\n上午国博，下午王府井。",
    "template", {"city": "北京", "travel_days": 2})
assert len(chunks) == 2           # Day1 + Day2
# 每个 chunk 的 metadata["day"] 分别是 "1" 和 "2"
# 每个 chunk 的 metadata["city"] = "北京"
# 每个 chunk 的 metadata["travel_days"] = 2
```


---

## 4. 数据入库：RagIngestionService 全流程

文件：`services/rag_ingestion.py`

### 4.1 create_source：建立知识来源

```python
def create_source(
    self, source_type, name, *,
    url=None, license_name=None,
    authorization_status="authorized", owner_user_id=None,
) -> RagSource:
```

创建一个 `RagSource` 记录并立即落库，然后立即用 `session.flush()` + `session.refresh()` 拿到 `source_id` 后才能继续导入文档。

三个关键字段：

| 字段 | 典型值 | 含义 |
|------|--------|------|
| `source_type` | `"official"` / `"guide"` / `"template"` / `"xiaohongshu"` | 来源类型 |
| `owner_user_id` | `None` / `"user_a"` | `None` = 公共知识库；`"user_a"` = 个人私有 |
| `authorization_status` | `"authorized"` / `"pending"` | 授权状态，检索时会展示 |

### 4.2 ingest_document：导入单篇文档

这是整个入库流程的核心。

#### 步骤一：计算内容哈希

```python
content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
```

用文档完整内容计算 SHA-256，这样同一来源下相同内容的文档不会产生重复记录。

#### 步骤二：查重判断

```python
existing = session.scalar(
    select(RagDocument).where(
        RagDocument.source_id == source_id,
        RagDocument.content_hash == content_hash,
    )
)
if existing is not None:
    job.status = "skipped"
    ...
    return existing, []
```

如果同一 source 下已有相同哈希的文档，直接跳过，返回已有 document，不创建新记录。这是幂等入库的关键。

#### 步骤三：归档原始文本

```python
raw_path = self._store_raw(source_id, title, content)
```

把原始文本保存到本地文件系统：

```text
rag_data/
  {source_id}/
    文档标题.txt
```

文件路径会写入 `rag_documents.raw_file_path`，方便后续追溯原文。

#### 步骤四：切块并写入 RagChunk

```python
chunks = self._create_chunks(
    session, document, content,
    document_type, metadata, embeddings,
)
```

关键逻辑：

- 调用 `RagChunker` 得到 `chunk_inputs`；
- 如果 embeddings 已传入（外部或调用方提前生成），则校验 `len(embeddings) == len(chunk_inputs)`；
- 逐行为每个 chunk 生成 `chunk_id`；
- 把外部元数据（`city`、`theme`、`travel_days`、`audience`、`poi_id` 等）直接萃取到 `RagChunk` 的字段里；
- `metadata_json` 保存完整元数据字典；
- `embedding` 字段存向量（可为空，后续批量回填）。

#### 步骤五：记录任务状态

每次导入都会创建 `RagIngestionJob`，字段包括：

```text
job_id          # 任务 ID
source_id       # 来源
document_id     # 关联文档
status          # "running" / "completed" / "skipped" / "failed"
error_message   # 错误信息
started_at      # 开始时间
finished_at     # 结束时间
```

---

### 4.3 ingestion 去重的意义

测试代码中明确验证：

```python
first, _ = service.ingest_document(source.source_id, "故宫", content, ...)
second, second_chunks = service.ingest_document(source.source_id, "故宫", same_content, ...)

assert second.document_id == first.document_id   # 复用已有记录
assert second_chunks == []                        # 没有新 chunk 产生
```

避免了同一来源重复入库造成的数据浪费，也保护了向量调用的成本。


---

## 5. 向量存储：EmbeddingService 与 pgvector

### 5.1 Embedding 如何生成？

文件：`services/embedding_service.py`

```python
class EmbeddingService:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for start in range(0, len(texts), self.settings.embedding_batch_size):
            batch = texts[start : start + self.settings.embedding_batch_size]
            response = self.client.embeddings.create(
                model=self.settings.embedding_model,      # text-embedding-v3
                input=batch,
                dimensions=self.settings.embedding_dimensions,  # 1024
            )
            vectors.extend([item.embedding for item in response.data])
        return vectors
```

核心配置（`config/settings.py`）：

| 配置项 | 默认值 | 含义 |
|--------|--------|------|
| `EMBEDDING_MODEL` | `text-embedding-v3` | 向量化模型 |
| `EMBEDDING_DIMENSIONS` | `1024` | 向量维度 |
| `EMBEDDING_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | API 地址（DashScope） |
| `EMBEDDING_BATCH_SIZE` | `16` | 每批次最多传入 16 个文本 |
| `DASHSCOPE_API_KEY` | 环境变量 | API 密钥 |

`embed_texts` 是批量版本；`embed_query` 是单条查询版本：

```python
def embed_query(self, text: str) -> list[float]:
    return self.embed_texts([text])[0]
```

### 5.2 PostgreSQL 中的向量存储

通过 Alembic 迁移脚本（`db/migrations/versions/692ae78a1fd7_add_rag_vector_and_ingestion.py`）可知：

```sql
ALTER TABLE rag_chunks ADD COLUMN embedding vector(1024);
ALTER TABLE rag_chunks ADD COLUMN tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', chunk_text)) STORED;
CREATE INDEX ix_rag_chunks_embedding_hnsw
  ON rag_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ix_rag_chunks_tsv_gin
  ON rag_chunks USING gin (tsv);
```

关键知识点：

1. **`vector(1024)`** — 使用 pgvector 扩展存储 1024 维向量；
2. **`vector_cosine_ops`** — 使用余弦距离做向量相似度计算；
3. **HNSW 索引** — 高效的近似最近邻搜索（Hierarchical Navigable Small World），适合大规模向量检索；
4. **`tsv` 生成列** — 自动从 `chunk_text` 生成全文检索向量，不用手动维护；
5. **GIN 索引** — 加速全文搜索查询。

注意：SQLite 中不存在 `vector` 和 `tsvector` 类型，所以 `embedding` 字段用 `.with_variant(JSON, "sqlite")` 降级为 JSON 存储。这意味着在 SQLite 测试环境里没有向量查询能力，检索依赖纯 SQL 模拟。

### 5.3 为什么向量存在 chunk 级别而不是 document？

因为检索的命中单元是 chunk。一个 document 可能包含 10 个 chunk，每个 chunk 有各自的 embedding，检索时可能是第 3 个 chunk 命中，而不是整个 document 命中。所以 embedding 必须粒子化到 chunk。

---

## 6. 数据检索：多路召回 + RRF 融合 + 可选 Rerank

文件：`services/rag_retrieval.py`

### 6.1 检索入口：`search()`

```python
def search(
    self, user_id, query, *,
    city=None, latitude=None, longitude=None,
    theme=None, travel_days=None, audience=None,
    top_k=None,
) -> list[RetrievedChunk]:
```

调用逻辑：

```text
search()
  ├─ 1. Dense 召回（向量语义） ─┐
  ├─ 2. BM25 召回（关键词）  ─┤→ RRF 融合 → 加载完整元数据 → 可选 Rerank → RetrievedChunk list
  ├─ 3. Geo 召回（地理距离） ─┤
  ├─ 4. Template 召回 ─────────┘
```

其中“多路召回 + RRF”是基础主链路；Rerank 已作为可选精排层接入，默认关闭。开启后由 `services/rerank_service.py` 调用文本排序接口，失败或超时时自动回退到原始 RRF 顺序。

### 6.2 四路召回详解

#### Dense（向量召回）

```python
def _dense(self, user_id, query_vector, top_k):
    """
    SELECT chunk_id
    FROM rag_chunks
    WHERE (owner_user_id IS NULL OR owner_user_id = :user_id)
      AND embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:vector AS vector)
    LIMIT :top_k
    """
```

- `<=>` 是 pgvector 的余弦距离操作符；
- `ORDER BY embedding <=> CAST(:vector AS vector)` 按语义相似度排序；
- 前提是 `embedding IS NOT NULL` 且不是 SQLite（因为 SQLite 没有向量查询能力）。

#### BM25 / 文本召回

PostgreSQL 专用，`chunk_text` 的 `tsv` 生成列参与：

```python
def _bm25(self, user_id, query, top_k):
    """
    SELECT chunk_id
    FROM rag_chunks
    WHERE (owner_user_id IS NULL OR owner_user_id = :user_id)
      AND (
        tsv @@ to_tsquery('simple', :token_query)
        OR chunk_text ILIKE :query
        OR (chunk_text ILIKE :like_0 OR chunk_text ILIKE :like_1 ...)
      )
    ORDER BY match_score DESC,
             ts_rank(tsv, to_tsquery('simple', :token_query)) DESC,
             chunk_id
    LIMIT :top_k
    """
```

中文处理细节（`_search_tokens`）：

- PostgreSQL 的 `simple` 分词器对中文是按整段切词的，效果差；
- 因此先拆出短词（如 `北京` 前2字），再从 `travel_terms` 白名单里补充旅游相关关键词；
- 然后用 `ILIKE '%token%'` 做兜底匹配。

#### Geo（地理召回）

```python
def _geo(self, user_id, latitude, longitude, top_k):
    """
    SELECT chunk_id
    FROM rag_chunks
    WHERE (owner_user_id IS NULL OR owner_user_id = :user_id)
      AND latitude IS NOT NULL AND longitude IS NOT NULL
    ORDER BY ((latitude - :lat)^2 + (longitude - :lng)^2)
    LIMIT :top_k
    """
```

按欧氏距离近似排序，近处景点优先。

#### Template（模板召回）

```python
def _templates(self, user_id, city, theme, travel_days, audience, top_k):
```

只在 `chunk_type = 'template'` 的范围内，按给定的 `city`/`theme`/`travel_days`/`audience` 精确过滤。只要任一字段不匹配就跳过。

### 6.3 RRF：把四路召回融合成一个排名

**Reciprocal Rank Fusion（RRF）** 是信息检索领域常用的多路融合算法。公式设计：

```text
RRF(d) = Σ₁/₄ 1 / (k + rank_i(d))
```

其中：

- `d` = 某个候选文档（chunk）；
- `rank_i(d)` = 该文档在第 i 路召回中的排名（1-based）；
- `k` = 常数（本项目用 `k=60`）；
- 四路召回各自贡献 1/4 权重。

公式的直观理解：

```text
一个 chunk 如果只被 dense 排第 1 → 贡献 1/(60+1) ≈ 0.016
一个 chunk 如果被 dense 排第 1、BM25 排第 2 → 贡献 2/(60+1)+1/(60+2) ≈ 0.033
一个 chunk 如果被 dense/BM25/template 三路都排前列 → 贡献更大
```

这样不需要把向量分数、全文分数、距离分数标准化到同一量纲，只用排名就能公平融合。

代码实现（`rag_retrieval.py`）：

```python
def _rrf(candidate_lists, *, k=60):
    scores = {}
    for candidates in candidate_lists:
        for rank, chunk_id in enumerate(candidates, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
```

### 6.4 Rerank：对 RRF 候选进行二次精排

#### 为什么 RRF 后还需要 Rerank？

RRF 擅长合并多路召回结果，但它只使用候选在各召回器中的**名次**，并不直接理解查询与 chunk 之间的细粒度语义。例如用户询问“适合老人、不要爬山的北京两日游”，向量召回可能因为“老人、北京、两日游”等词语召回包含登长城的内容，RRF 也可能因为它在多路结果中排名靠前而保留它。Reranker 会重新阅读完整的“查询 + 候选文本”，理解“不要爬山”这一否定约束，并把不符合条件的内容降权。

Embedding 召回通常采用双塔结构：查询和文档分别编码成向量，可以预先计算文档向量，因此速度快，适合从大规模知识库中粗筛。Reranker 通常采用交叉编码方式：将查询和一个候选 chunk 一起送入模型，让两段文本充分交互后输出相关性分数，因此判断更准确，但每次查询都要逐条计算候选，延迟和成本更高。二者的分工是：

```text
Embedding / BM25 / Geo / Template：高召回，尽量不要漏掉答案
RRF：合并不同量纲、不同来源的候选排名
Reranker：高精度，从少量候选中选出最相关内容
```

#### 在本项目中的推荐位置

```text
四路各召回 Top 20
        ↓
RRF 融合并截取 Top 15
        ↓
加载候选 chunk_text 和必要元数据
        ↓
Reranker(query, candidates) 逐条打分
        ↓
按 rerank_score 降序排列，保留 Top 6
        ↓
结合上下文预算，最终向 ContextBuilder 注入约 4 条
```

Rerank 必须放在权限和硬条件过滤之后。`owner_user_id`、授权状态、城市、旅行天数等约束不能交给模型“软判断”；否则即使 Reranker 相关性很高，也可能返回用户无权查看或业务条件不满足的内容。Reranker 主要负责语义相关性，时效性、来源可信度、地理距离和互动热度可以作为独立业务信号，与模型分数进行可解释组合：

```text
final_score = rerank_score
            + freshness_weight
            + source_quality_weight
            + popularity_weight
```

第一版建议只使用 `rerank_score` 排序并保留原始 RRF 分数用于观测，避免在没有离线评测前引入过多人工权重。若 Rerank 服务超时、报错或被关闭，应直接退回 RRF 顺序，保证检索链路可用。

#### 实现方式与验收条件

项目将 Reranker 封装在 `services/rerank_service.py`，输入 `query` 和候选 chunk 列表，输出与候选一一对应的原始索引和相关性分数；检索层负责调用、排序和降级。当前使用 DashScope 文本排序 HTTP 协议，默认模型为 `qwen3-rerank`，接口 URL 通过配置传入，因此运行代码不绑定具体业务空间。

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `RAG_RERANK_ENABLED` | `false` | 是否启用精排，可灰度开启 |
| `RAG_RERANK_BASE_URL` | 空 | 百炼业务空间对应的完整文本排序接口 URL |
| `RAG_RERANK_MODEL` | `qwen3-rerank` | Rerank 模型名称 |
| `RAG_RERANK_CANDIDATE_K` | 15 | 从 RRF 送入精排的候选数 |
| `RAG_RERANK_TOP_K` | 6 | 精排后保留数量 |
| `RAG_RERANK_TIMEOUT_SECONDS` | 5 秒 | 超时后回退 RRF 排名 |

正式开启前，应使用 `evaluation/datasets/rag_golden.json` 比较开启前后的 Recall@K、MRR、nDCG 和最终答案引用准确率，同时记录 P95 延迟、失败率和单次查询成本。只有相关性收益明显且延迟、成本可接受时，才适合默认开启。开发计划中的目标值也是“Rerank Top-K 6、最终上下文数量 4”。

### 6.5 用户隔离：私有 vs 公共

四路召回的 SQL 都带统一过滤：

```sql
WHERE (owner_user_id IS NULL OR owner_user_id = :user_id)
```

这意味着：

- **`owner_user_id IS NULL`**：公共知识库，所有用户都能看到；
- **`owner_user_id = :user_id`**：某个用户的私有数据，只有该用户能看到。

`RagRepository` 数据访问层也实现了同样逻辑，不仅是查询层，实体过滤也是同样的 scope。


---

## 7. 检索结果：RetrievedChunk 与元数据加载

### 7.1 _load_chunks：加载完整上下文

RRF 融合选出 top-k chunk_id 后，还需要加载完整元数据：

```python
def _load_chunks(self, user_id, chunk_ids):
    """
    SELECT c.chunk_id, c.document_id, c.owner_user_id,
           c.chunk_text, c.chunk_type,
           c.city, c.theme, c.travel_days, c.audience,
           s.name as source_name,
           coalesce(sn.canonical_url, s.url) as source_url,
           s.authorization_status,
           coalesce(sn.published_at, d.published_at) as published_at,
           coalesce(sn.fetched_at, d.updated_at) as fetched_at,
           sn.platform as social_platform,
           metrics.likes, metrics.collects, metrics.comments, metrics.shares
    FROM rag_chunks c
    JOIN rag_documents d ON d.document_id = c.document_id
    JOIN rag_sources s   ON s.source_id = d.source_id
    LEFT JOIN social_notes sn ON sn.document_id = d.document_id
    LEFT JOIN LATERAL (
        SELECT m.likes, ... FROM social_metric_snapshots m
        WHERE m.social_note_id = sn.social_note_id
        ORDER BY m.captured_at DESC LIMIT 1
    ) metrics ON true
    WHERE c.chunk_id = ANY(:chunk_ids)
      AND (c.owner_user_id IS NULL OR c.owner_user_id = :user_id)
    """
```

这张 SQL 有几个关键设计：

1. `coalesce(sn.canonical_url, s.url)` ：优先使用社交笔记的规范链接，否则用来源链接；
2. `coalesce(sn.published_at, d.published_at)` ：优先使用笔记发布时间，否则用文档入库时间；
3. `left join lateral` + `order by captured_at desc limit 1` ：拿到每个社交笔记最新的指标快照。

### 7.2 RetrievedChunk 结构体

```python
@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    owner_user_id: str | None
    chunk_text: str
    chunk_type: str
    score: float           # RRF 融合得分
    rank: int
    city: str | None
    theme: str | None
    travel_days: int | None
    audience: str | None
    source_name: str | None
    source_url: str | None
    source_authorization_status: str | None
    published_at: str | None
    fetched_at: str | None
    social_platform: str | None
    likes: int | None
    collects: int | None
    comments: int | None
    shares: int | None
```

每个检索结果都带溯源信息，下游生成工具（如 `plan_itinerary`）的 prompt 中能展示来源，而不是让模型凭空编造。

---

## 8. RAG 如何接入 Agent 工作流

### 8.1 谁在调用 RAG？

文件：`multi_agent/executor.py`

```python
rag_results = self.rag_retrieval.search(
    state.user_id,
    user_input,
    city=state.travel_request.destination,
    theme=state.travel_request.travel_style,
    travel_days=state.travel_request.travel_days,
) if route.tool_name in {"plan_itinerary", "refine_itinerary",
                          "recommend_destination", "estimate_budget"} else []
```

触发条件：只有以下四类工具会被 RAG 检索：

- `plan_itinerary`（新行程生成）
- `refine_itinerary`（行程调整）
- `recommend_destination`（目的地推荐）
- `estimate_budget`（预算估算）

这些工具都需要 LLM 基于外部知识来生成，如果只是工具调用结果（如天气查询、POI 搜索），不需要检索。

### 8.2 RAG 结果如何进入上下文

`ContextBuilder.build()`（`services/context_builder.py`）会把 `rag_results` 包装成一个 `rag_knowledge` 分片：

```python
rag_results = extra.get("rag_results")
if rag_results:
    sections.append(
        ContextSection("rag_knowledge",
            self._format_rag_results(rag_results),
            45)   # priority 45，低于 user_profile(50) 但高于通用 extra(40)
    )
```

`_format_rag_results` 渲染后的样子：

```text
检索到的参考知识：
- 周一闭馆，需要提前预约。
  来源：北京文旅（https://example.com），授权状态：authorized，更新时间：2026-09-30
- 门票旺季 60 元。
  来源：北京文旅，...
```

RAG 知识块和长期记忆块（`long_term_memory`）在上下文中的优先级不同：

| 分片 | 优先级 | 数据内容 |
|------|--------|----------|
| `user_profile` | 50 | 用户长期偏好 |
| `long_term_memory` | 48 | 用户确认过的长期记忆 |
| `rag_knowledge` | 45 | 外部事实和攻略 |
| 其他 extra | 40 | 其他任意上下文 |

### 8.3 为什么 embedding 在查询时额外生成，不在 prompt 里？

```python
if self.embedding_service is not None and not self.database.url.startswith("sqlite"):
    query_vector = self.embedding_service.embed_query(query)
    dense_ids = self._dense(user_id, query_vector, settings.rag_dense_top_k)
```

有两层含义：

1. **查询向量与入库向量必须同一模型、同一维度**，所以调用方（`api/rag.py`、`tools`、`manage_rag.py`）统一调用 `EmbeddingService.embed_query()`；
2. **SQLite 环境下不走 dense**，因为 SQLite 没有向量索引。

---

## 9. 配置与运行约束

### 9.1 关键配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `RAG_DENSE_TOP_K` | 20 | dense 召回数 |
| `RAG_BM25_TOP_K` | 20 | BM25/文本召回数 |
| `RAG_GEO_TOP_K` | 20 | 地理召回数 |
| `RAG_TEMPLATE_TOP_K` | 20 | 模板召回数 |
| `RAG_RRF_TOP_K` | 15 | 未启用 Rerank 时的最终返回数量 |
| `RAG_RERANK_ENABLED` | `false` | 是否启用精排 |
| `RAG_RERANK_BASE_URL` | 空 | 文本排序服务的完整接口 URL |
| `RAG_RERANK_MODEL` | `qwen3-rerank` | 精排模型 |
| `RAG_RERANK_CANDIDATE_K` | 15 | RRF 送入精排的候选数量 |
| `RAG_RERANK_TOP_K` | 6 | 精排后默认返回数量 |
| `RAG_RERANK_TIMEOUT_SECONDS` | 5 | 精排请求超时秒数；失败后回退 RRF |
| `RAG_MIN_RELEVANCE` | 0.0 | 相关性最低阈值（0 = 不过滤） |
| `EMBEDDING_MODEL` | `text-embedding-v3` | 向量模型 |
| `EMBEDDING_DIMENSIONS` | 1024 | 向量维度（必须与模型一致） |
| `EMBEDDING_BATCH_SIZE` | 16 | 每批向量化的最大文本数 |

### 9.2 当前实现的限制

1. **SQLite 不支持向量/全文检索**
  - SQLite 中 `embedding` 只能存 JSON，无法走 `<=>` 向量查询；
  - 本地开发或测试时此路径走纯 fallback 文本匹配。

2. **BM25 依赖 PostgreSQL 全文索引**
  - `to_tsquery`/`ts_rank` 是 PG 专有；
  - 如果换数据库（MySQL）需要重写 BM25 实现。

3. **地理召回只做欧氏距离**
  - `ORDER BY ((lat - :lat)^2 + (lng - :lng)^2)` 不是球面距离（Haversine），在城市尺度下误差可忽略，但不适合大距离。

4. **互动指标未参与排序**
  - `likes` / `collects` 等社交指标只是附加在 `RetrievedChunk` 上返回，目前不影响 RRF 得分；
  - 可以演进为在 `final_score = semantic + freshness + quality + log(1 + likes/collects)` 中引入热度权重。

5. **Rerank 依赖外部服务且默认关闭**
  - 开启前必须配置 `DASHSCOPE_API_KEY` 和业务空间对应的 `RAG_RERANK_BASE_URL`；
  - 当前已经实现开关、超时和异常回退，但生产环境仍需补充 P95 延迟、失败率和调用成本监控。


---

## 10. 相关文件索引

### 核心服务层

| 文件 | 职责 |
|------|------|
| `services/rag_chunker.py` | 按事实/攻略/模板三种规则切块 |
| `services/rag_ingestion.py` | 建Source、去重、切块、归档、落库 |
| `services/rag_retrieval.py` | dense/BM25/geo/template 四路召回、RRF 融合与可选 Rerank 编排 |
| `services/rerank_service.py` | 调用文本排序接口、校验响应并返回精排索引与分数 |
| `services/embedding_service.py` | 向量化，调用 OpenAI 兼容 API |
| `services/mcp_client.py` | MCP 客户端封装（小红书数据采集） |
| `services/xhs_ingestion.py` | 小红书笔记采集、去重、入库 |

### 数据模型与仓储

| 文件 | 职责 |
|------|------|
| `db/models.py` | RagSource / RagDocument / RagChunk / RagIngestionJob / SocialNote |
| `db/migrations/versions/692ae78a1fd7_*.py` | 向量字段和全文索引的迁移脚本 |
| `repositories/rag_repository.py` | RAG CRUD + 用户隔离 scope |

### 接口与工具

| 文件 | 职责 |
|------|------|
| `api/rag.py` | HTTP API：检索、创建来源、导入文档、删除、列表 |
| `scripts/manage_rag.py` | CLI：创建来源 / 导入 / 检索 / 回填 embedding / 删除 |
| `multi_agent/executor.py` | 在生成类工具前调用 RAG |
| `services/context_builder.py` | 把 RAG 结果包装成 prompt 上下文 |

### 前端与测试

| 文件 | 职责 |
|------|------|
| `frontend/src/views/KnowledgeView.vue` | 知识库管理页面（上传/查看/删除） |
| `tests/unit/test_rag_ingestion.py` | 切块规则和去重测试 |
| `tests/unit/test_rag_repository.py` | CRUD 和用户隔离测试 |
| `tests/unit/test_rag_retrieval.py` | RRF 融合和用户隔离测试 |

### 评测

| 文件 | 职责 |
|------|------|
| `evaluation/rag.py` | Recall@K / Precision@K / nDCG / 引用准确率 / 来源可追溯率 |
| `evaluation/dataset_builder.py` | 从真实知识库构建银集和候选金集 |
| `scripts/build_rag_evalsets.py` | 建立与校验 RAG 评测集 |

---

## 11. 快速上手指引

### 11.1 导入一条知识

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_rag ingest src_d23778c1f7004413 `
  D:\docs\故宫开放信息.txt `
  --title "故宫开放信息" `
  --document-type fact `
  --metadata '{\"city\":\"北京\",\"poi_id\":\"B000A8UIN8\"}' `
  --embed
```

### 11.2 检索一条知识

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_rag search demo_traveler `
  "故宫周一开放吗" --city 北京 --top-k 5
```

### 11.3 创建来源

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_rag create-source official `
  北京文旅 --url https://example.com --owner-user-id demo_traveler
```

---

## 12. 常见问题 FAQ

**Q1：RAG 和 Memory 有什么区别？**

- **RAG**：检索外部资料（攻略、官方说明、真实笔记），回答「世界上有什么」；
- **Memory**：保存用户过去说过的偏好和行为，回答「这个用户是什么样的人」。

在 Agent 工作流中二者互补：LLM 同时拿到 user_profile/memory + rag_knowledge，既能个性化又不编造事实。

**Q2：为什么 PostgreSQL 需要 pgvector 而不是 FAISS？**

pgvector 是 PostgreSQL 原生向量扩展，可以：

- 与关系数据（`owner_user_id`、`city`、`chunk_type`）JOIN 检索；
- 用 SQL 一次搞定过滤 + 向量排序；
- 不需要额外维护一个独立的向量索引服务。

FAISS 更适合纯向量检索但不方便做多条件 JOIN。

**Q3：RRF 为什么不用向量分数直接加权？**

因为不同的召回器分数量纲不同：

- 向量余弦相似度是 `[0,1]`；
- BM25 是 `ts_rank` 值，通常远大于 1；
- 地理距离是「越小越好」；
- 模板是「命中/未命中」。

直接加权没有意义。RRF 只比较排名，天然消除了量纲差异。

**Q4：如果知识库里没有相关 chunk 怎么办？**

`RagRetrievalService.search()` 会返回空列表 `[]`，此时：

- `ContextBuilder` 不会创建 `rag_knowledge` 分片；
- LLM 只能依靠内部知识和当前会话输入；
- prompt 中也不会出现「检索到的参考知识」段落。

**Q5：RRF 和 Reranker 是不是重复排序？**

不是。RRF 使用各召回器给出的名次进行低成本融合，解决向量分数、BM25 分数和地理距离不能直接相加的问题；Reranker 则重新联合阅读查询与候选文本，判断细粒度语义相关性。前者负责形成稳定候选集，后者负责精排少量候选。没有 Reranker 时系统仍可使用 RRF 正常工作；启用 Reranker 后，RRF 排名也应保留用于降级和效果对照。

---

## 13. 总结：RAG 在本项目的本质

```text
RAG = 先检索（4路召回 + RRF + 可选 Rerank）
     再增强（RetrievedChunk + source/时间/互动指标）
     再生成（ContextBuilder 注入 LLM prompt）
```

在本项目中，RAG 不是简单的「向量库里搜一搜」，而是一个带有：

- **分层数据模型**（Source → Document → Chunk）；
- **多样化召回策略**（向量 / 文本 / 地理 / 模板）；
- **可解释的融合方式**（RRF，无归一化问题）；
- **可选精排能力**（Rerank 默认关闭，调用异常时回退 RRF）；
- **权限隔离**（owner_user_id 公共/私有）；
- **溯源能力**（source_url + published_at + fetched_at）；
- **可观测指标**（Recall / Precision / nDCG / 引用准确率 / 来源可追溯率）；

的完整生产级系统。掌握这九个方面，就等于掌握了本项目 RAG 的完整实现。
