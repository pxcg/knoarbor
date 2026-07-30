# 报告与台账契约

KnoArbor 将流程结果记录在两个互补表面：

- 面向人的 Markdown 报告，位于 `maintenance/reports/**`；
- 面向机器的追加式 JSONL 台账，位于 `.knoarbor/ledgers/**`。

报告解释一次运行发生了什么。台账保存稳定的运行记录，供 UI、CLI、Token 分析、趋势分析和后续恢复使用。

## 报告目录

```text
maintenance/
  reports/
    ingest/
    lint/
    query/
    run-failure/
  archives/
```

| 流程 | 目录 | 用途 |
| --- | --- | --- |
| ingest | `maintenance/reports/ingest/` | 资料处理、分段、索引元数据抽取、确定性编译校验、source revision 提交、物化请求、局部 lint、Token 摘要。 |
| lint | `maintenance/reports/lint/` | 问题、修复计划、所有者流程执行结果、修复后复扫、指标与警告。 |
| query | `maintenance/reports/query/` | 查询候选、答案集合轨迹、指导信息、缺口、上下文包。 |
| run-failure | `maintenance/reports/run-failure/` | 流程专属报告尚未生成时的通用早期失败记录。 |

流程内的早期失败通常写入对应流程目录，并标记失败状态。通用运行时失败使用 `run-failure`。

## 台账目录

```text
.knoarbor/
  ledgers/
    ingest.jsonl
    lint_run.jsonl
    query.jsonl
    query_feedback.jsonl
    token.jsonl
  runs/
  ingest/
  locks/
  logs/
```

稳定台账 schema：

| 台账 | Schema |
| --- | --- |
| `ingest.jsonl` | `ingest_run.v1` |
| `lint_run.jsonl` | `lint_run_record.v1` |
| `query.jsonl` | `query_record.v2` |
| `query_feedback.jsonl` | `query_feedback.v1` |
| `token.jsonl` | `token_ledger.v1` |
| 流程台账中的失败记录 | `run_failure_record.v1` |

`token_analysis.v1` 是从 Token 台账和历史运行台账派生出的分析响应。

## 失败产物

失败产物遵循同一边界：

- 失败报告：面向用户的 Markdown 解释；
- 失败台账行：包含错误码、阶段、请求摘要、可重试性和提示的机器记录。

失败记录使用 `run_failure_record.v1`。它们在常规流程结果生成前写入，保留 UI、CLI 和日志解释失败运行所需的上下文。

## Ingest 物化

Ingest 报告区分事实提交和确定性物化。`source_revision` 标识已经提交的
raw-grounded 事实，source 条目记录 vault 物化已经被请求；最终物化告警由事务运行记录承载。
重建 projection 与 machine index 不调用模型，也不会回滚已经提交的 source revision。

## 职责归属

- `audit/*_report.py` 构建面向人的报告和流程台账行。
- `audit/run_failure.py` 构建早期失败产物。
- `audit/token_ledger.py` 构建 Token 台账行和派生 Token 分析。
- `storage/ledger.py` 负责追加式 JSONL 写入。
- `storage/vault_layout.py` 负责物理路径。

UI 和 API 适配器通过服务层读取这些产物，并呈现报告和台账，不重新定义存储布局。
