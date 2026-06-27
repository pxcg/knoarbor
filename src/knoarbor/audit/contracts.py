from __future__ import annotations

from knoarbor.storage.vault_layout import ledger_relative_path


REPORT_SCHEMA_VERSION = "report_contract.v1"

REPORT_KINDS = ("ingest", "lint", "query", "run-failure")

REPORT_DIRECTORIES = {
    "ingest": "maintenance/reports/ingest",
    "lint": "maintenance/reports/lint",
    "query": "maintenance/reports/query",
    "run-failure": "maintenance/reports/run-failure",
}

LEDGER_SCHEMA_VERSIONS = {
    "ingest": "ingest_run.v1",
    "lint": "lint_run_record.v1",
    "query": "query_record.v1",
    "query_feedback": "query_feedback.v1",
    "token": "token_ledger.v1",
    "token_analysis": "token_analysis.v1",
    "run_failure": "run_failure_record.v1",
}

LEDGER_PATHS = {
    "ingest": ledger_relative_path("ingest"),
    "lint": ledger_relative_path("lint_run"),
    "query": ledger_relative_path("query"),
    "token": ledger_relative_path("token"),
}

HUMAN_REPORT_ROOT = "maintenance/reports"
MACHINE_RUNTIME_ROOT = ".knoarbor"
