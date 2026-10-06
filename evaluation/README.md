# TravelMind 评测体系

阶段 9 的离线评测覆盖 RAG、行程质量和长期 Memory。评测只读取业务数据库，不会修改已导入的 RAG、行程或记忆。

## 运行基线

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_evals --no-embedding
```

使用 DashScope 向量召回运行完整 RAG 评测：

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_evals
```

只运行某个部分：

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_evals --sections rag --no-embedding
.\.venv\Scripts\python.exe -m scripts.manage_evals --sections itinerary
.\.venv\Scripts\python.exe -m scripts.manage_evals --sections memory
```

报告默认生成在 `outputs/evaluations/baseline.json` 和同名 Markdown 文件。

## RAG 黄金集标注

### 从当前知识库建立银集和候选金集

查看符合评测要求的城市/主题覆盖：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets coverage `
  --source-id src_d23778c1f7004413
```

使用 DeepSeek 从真实笔记正文生成自然问题，并按城市和主题分层抽样：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets build `
  --source-id src_d23778c1f7004413 `
  --query-mode llm `
  --silver-per-cell 6 `
  --gold-per-cell 2
```

该命令生成：

- `datasets/rag_silver.json`：程序校验证据和来源的自动银集；
- `datasets/rag_golden.json`：从银集中分层抽取的候选金集；
- `datasets/rag_golden_review.csv`：适合在 Excel 中逐条审核的问题、证据和来源表。

重新采集知识库后，可检查数据集中的文档和逐字证据是否仍有效：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets validate `
  --source-id src_d23778c1f7004413 `
  --dataset evaluation\datasets\rag_golden.json
```

银集的 `synthetic_validated` 仅表示程序校验通过，不代表人工金标准。候选金集必须逐条确认：问题自然且无歧义、证据确实支持问题、目标文档是合理相关项、没有泄漏完整标题。审核完成后，将每条 `review_status` 改为 `approved`，全部通过后再把顶层 `calibration_status` 改为 `approved`。

推荐直接打开 `rag_golden_review.csv`，逐行修改问题并将 `review_status` 填为 `approved` 或 `rejected`。完成后执行：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets finalize-review `
  --source-id src_d23778c1f7004413
```

命令会把 CSV 中修改过的问题和证据回写到 `rag_golden.json`，剔除 `rejected` 行，并再次对照数据库校验。只要还有未审核行，数据集仍保持 `pending_human_review`；所有保留项均通过后，才会自动标记为 `approved`。

如果已经逐条检查完毕，只在有问题的行填写了 `review_note`，其余行保持默认状态，可以执行：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_rag_evalsets finalize-review `
  --source-id src_d23778c1f7004413 `
  --approve-unmarked `
  --reject-noted `
  --update-review-file
```

该快捷方式会批准没有意见的行、剔除带意见的行，并将最终状态同步回 CSV。只应在确认整张表已经人工检查完成时使用。

成都等覆盖不足的城市不会为了凑数而进入首版评测集；正文和主题覆盖达到门槛后，重新运行构建命令即可纳入下一版本。

`datasets/rag_golden.json` 中每条 case 至少需要一个 `relevant` 规则。正式比较模型或 Reranker 前，建议用检索结果中的稳定 `chunk_id` 或 `document_id` 标注；关键词规则适合试点期，但精度较低。

支持的相关性条件：

- `chunk_id`、`document_id`、`source_name`、`source_url`：精确匹配；
- `contains_all`：正文必须包含全部关键词；
- `contains_any`：正文至少包含一个关键词；
- `relevance`：分级相关性，供 nDCG 使用。

人工复核完成后，把 `calibration_status` 从 `draft` 改为 `approved`。在此之前，报告会明确提示分数只能作为试运行基线。

## 指标口径

- `Recall@K`：K 个结果覆盖了多少人工标注相关项；
- `Precision@K`：K 个位置中相关结果的比例；
- `nDCG@K`：相关结果是否排在更靠前的位置；
- `citation_accuracy`：带完整来源的结果中，能被黄金规则支持的比例；
- `source_traceability`：结果中同时具有 document ID、来源名和来源链接的比例；
- 行程指标按整份行程统计时间冲突、预算超限和路线未核验；
- Memory 指标统计错误召回、冲突优先级与跨用户读取泄漏。
