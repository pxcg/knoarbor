# Report And Ledger Contract

KnoArbor records workflow outcomes in two complementary surfaces:

- human-readable Markdown reports under `maintenance/reports/**`;
- machine-readable append-only ledgers under `.knoarbor/ledgers/**`.

Reports explain what happened. Ledgers preserve stable runtime records for UI,
CLI, token analysis, trend analysis, and later recovery.

## Report Layout

```text
maintenance/
  reports/
    ingest/
    lint/
    query/
    run-failure/
  archives/
```

Report directories:

| Flow | Directory | Purpose |
| --- | --- | --- |
| ingest | `maintenance/reports/ingest/` | Source processing, segmentation, page planning, write gate, writes, scoped lint, token summary. |
| lint | `maintenance/reports/lint/` | Deterministic issues, semantic candidates, review decisions, applied operations, diffs, verification, rescan. |
| query | `maintenance/reports/query/` | Query candidates, answer-set trace, guidance, gaps, context pack. |
| run-failure | `maintenance/reports/run-failure/` | Generic early workflow failures when a flow-specific report cannot be produced. |

Flow-specific early failures are normally written into the corresponding flow
directory with a failed status. Generic runtime failures use `run-failure`.

## Ledger Layout

```text
.knoarbor/
  ledgers/
    ingest.jsonl
    lint_run.jsonl
    query.jsonl
    query_feedback.jsonl
    token.jsonl
  runs/
  checkpoints/
  queue/
  locks/
  logs/
```

Stable ledger schemas:

| Ledger | Schema |
| --- | --- |
| `ingest.jsonl` | `ingest_run.v1` |
| `lint_run.jsonl` | `lint_run_record.v1` |
| `query.jsonl` | `query_record.v1` |
| `query_feedback.jsonl` | `query_feedback.v1` |
| `token.jsonl` | `token_ledger.v1` |
| failure records inside flow ledgers | `run_failure_record.v1` |

`token_analysis.v1` is a derived analysis response built from token ledger
records and historical run ledgers.

## Failure Artifacts

Failure artifacts use the same boundary:

- failure report: Markdown explanation for users;
- failure ledger row: machine-readable record with error code, stage, request
  summary, retryability, and hint.

Failure records use `run_failure_record.v1`. They are written before normal
workflow results exist, preserving enough context for UI, CLI, and logs to
explain the failed run.

## Ownership

- `audit/*_report.py` builds human-readable reports and flow ledger rows.
- `audit/run_failure.py` builds early failure artifacts.
- `audit/token_ledger.py` builds token ledger rows and derived token analysis.
- `storage/ledger.py` owns append-only JSONL writes.
- `storage/vault_layout.py` owns physical paths.

UI and API adapters read these artifacts through service layers. They present
reports and ledgers without redefining their storage layout.
