# 契约总览

本文是 KnoArbor 当前冻结契约的中文入口。详细字段以
[`../CONTRACTS.md`](../CONTRACTS.md) 为准；本页用于说明各契约的职责边界。

## 契约层

| 层级 | 冻结对象 |
| --- | --- |
| 知识库目录 | `raw/`、`wiki/`、`maintenance/`、`.knoarbor/` |
| Wiki 页面 | `wiki/pages/*.md` |
| Source Digest | `wiki/sources/*.md` |
| Raw 附件 | `raw/derived/assets/**` 与 `raw/derived/metadata/**` |
| 机器索引 | `.knoarbor/index/manifest.json` 与 `graph_index.json` |
| Ingest | 从 Source Input 到 Report / Checkpoint Commit 的阶段对象 |
| Query | 图索引召回、BM25 重排、answer-set 输出 |
| Chat | 工具调用、evidence pack、回答、引用解析 |
| 报告与账本 | Markdown 报告、JSONL 账本、失败记录、token 账本 |
| API | method-aware 本地 HTTP API |
| UI | Chat、Flows、Knowledge、Settings 四类界面 |

## 目录边界

```text
vaults/<id>/
  raw/
    inbox/
      notes/
      documents/
      chats/
      media/
    derived/
      markdown/
      excerpts/
      assets/
      metadata/
  wiki/
    pages/
    sources/
  maintenance/
    reports/
    archives/
  .knoarbor/
    index/
    ledgers/
    checkpoints/
    runs/
    queue/
    locks/
    logs/
    chat/sessions/
```

- `raw/inbox/` 保存用户提供或导入的原始资料。
- `raw/derived/` 保存预处理器和系统生成的 Markdown、摘录、附件和元数据。
- `wiki/pages/` 保存最终知识页。
- `wiki/sources/` 保存来源审计页。
- `maintenance/` 保存运行报告。
- `.knoarbor/` 保存机器状态。

## Wiki 页面

Wiki 页面保存可维护知识，核心是 `Claims`。

```md
## Summary
## Claims
## Entities
## Relations
## Evidence
## Synthesis
## Attachments
```

`Claims` 是页面主内容；`Entities`、`Relations`、`Evidence`、`Synthesis`
和 `Attachments` 围绕 claims 提供连接、证据和阅读表达。

## Source Digest

Source Digest 保存 raw 到 wiki 的审计记录。

```md
## Source Identity
## Audit Summary
## Source Units
## Contribution Map
## Unresolved / Rejected
## Attachments
## Raw Source
```

附件表使用：

```md
| Attachment | Type | Topic | Description | Source Range | Status |
```

路径、hash、MIME、坐标、OCR/VLM 原始输出和 parser 细节保存在
`raw/derived/metadata/**` 与机器元数据中。

## 检索与对话

Query 是 model-free 的证据检索层：

```text
query -> graph/index recall -> BM25 rerank -> answer-set
```

Query 响应使用 `wiki_query.v1`。核心输出为：

- `results`：排序后的检索候选。
- `primary_pages`：直接承载回答的维护页。
- `supporting_pages`：补充机制、细节、比较和上下文的维护页。
- `source_pages`：用于溯源的 source digest。
- `answer_scope`：问题范围和知识库范围。
- `answer_set`：回答构造所需的页面角色计划。
- `evidence_coverage`：证据覆盖、缺口和置信信号。
- `context_pack`：给调用方继续组织回答的文本证据包。

Chat 是回答层：

```text
message -> tool plan -> evidence pack -> answer model -> citation resolver
```

Chat evidence pack 使用 `chat_evidence_pack.v1`。`primary_pages`、
`supporting_pages`、`source_pages` 是模型回答的证据输入；
`citation_pages` 是可引用页面顺序；`further_results` 是导航材料。

引用解析器负责把模型正文中的 `[1]` 等引用映射为公开引用列表，
并通过 `hidden_evidence_count` 记录已观测但未公开展示的证据数量。

## Ingest 运行观察

Ingest 运行观察的稳定阶段为：

```text
input -> segment -> normalize_agent -> atom_agent -> retrieval
  -> plan_agent -> draft_agent -> review_agent -> write_gate -> write
```

稳定事件类型为：

- `ingest_step_started`
- `ingest_step_finished`
- `ingest_step_skipped`

这些名称用于运行监控、报告和 UI adapter 之间的契约对齐。

图索引用于定位页面，Markdown 页面用于解释知识。

## 报告与账本

报告与账本的完整契约见 [`../REPORT_CONTRACT.md`](../REPORT_CONTRACT.md)。

- `maintenance/reports/**` 保存人可读 Markdown 报告。
- `.knoarbor/ledgers/**` 保存追加式机器账本。
- `.knoarbor/runs/**`、`queue/**`、`locks/**`、`logs/**` 保存运行生命周期状态。
- 失败记录使用 `run_failure_record.v1`。
- token 分析由 `token_ledger.v1` 和历史流程账本派生。
