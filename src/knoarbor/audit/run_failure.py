from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.audit.reports import write_maintenance_report
from knoarbor.core.errors import error_info
from knoarbor.core.schemas.run_monitor import RunFlow
from knoarbor.storage.ledger import append_jsonl_ledger
from knoarbor.storage.wiki_index import relative_wiki_path


DEFAULT_FAILURE_LEDGER_PATHS: dict[RunFlow, str] = {
    "ingest": "maintenance/ingest_ledger.jsonl",
    "lint": "maintenance/lint_run_ledger.jsonl",
    "query": "maintenance/query_ledger.jsonl",
}


def write_run_failure_artifacts(
    vault_path: Path,
    *,
    flow: RunFlow,
    request: Any,
    exc: BaseException,
    run_id: str | None = None,
    stage: str | None = None,
    append_ledger: bool = True,
    write_report: bool = True,
    report_path: str | None = None,
    ledger_path: str | None = None,
) -> tuple[str | None, str | None]:
    """Write a user-visible failure report for workflow failures before normal results exist."""

    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    record = build_run_failure_record(flow=flow, request=request, exc=exc, run_id=run_id, stage=stage)
    effective_ledger_path = ledger_path or DEFAULT_FAILURE_LEDGER_PATHS[flow]
    written_ledger = append_jsonl_ledger(vault_path, effective_ledger_path, record) if append_ledger else None
    effective_report_path = report_path or f"maintenance/{flow}_run_report_{run_id}.md"
    written_report = (
        write_maintenance_report(vault_path, f"{flow}_run", render_run_failure_report(record), effective_report_path)
        if write_report
        else None
    )
    return (
        relative_wiki_path(vault_path, written_ledger) if written_ledger else None,
        relative_wiki_path(vault_path, written_report) if written_report else None,
    )


def build_run_failure_record(
    *,
    flow: RunFlow,
    request: Any,
    exc: BaseException,
    run_id: str,
    stage: str | None = None,
) -> dict[str, object]:
    info = error_info(exc)
    info.pop("http_status", None)
    return {
        "schema_version": "run_failure_record.v1",
        "run_id": run_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "flow": flow,
        "status": "failed",
        "stage": stage or "failed",
        "request": _compact_request(request),
        "error": info,
        "warnings": [f"{flow} run failed before a normal workflow result could be written."],
    }


def render_run_failure_report(record: dict[str, object]) -> str:
    error = _as_dict(record.get("error"))
    request = _as_dict(record.get("request"))
    flow = str(record.get("flow") or "workflow")
    title = {"ingest": "Ingest Report", "lint": "Lint Run Report", "query": "Query Report"}.get(flow, "Run Report")
    lines = [
        f"# {title}",
        "",
        f"- run_id: {record.get('run_id')}",
        f"- created_at: {record.get('created_at')}",
        f"- flow: {flow}",
        f"- status: {record.get('status')}",
        f"- stage: {record.get('stage')}",
        f"- error_type: {error.get('error_type')}",
        f"- error_code: {error.get('code')}",
        f"- error_category: {error.get('category')}",
        f"- retryable: {error.get('retryable')}",
        "",
        "## Failure",
        "",
        f"- error: {error.get('message') or 'Unknown error'}",
        f"- hint: {error.get('hint') or 'Check the runtime logs and request payload.'}",
        "",
        "## Request",
        "",
        *_format_request_lines(request),
        "",
        "## Suggested Actions",
        "",
        "- Check the error code, stage, and request summary above.",
        "- If the error is retryable, rerun after the provider or external service recovers.",
        "- If this is a configuration, vault, or source error, fix the configuration before rerunning.",
        "",
        "## Execution",
        "",
        "- No workflow changes were applied after this failure report was written.",
    ]
    return "\n".join(lines) + "\n"


def _compact_request(request: Any) -> dict[str, object]:
    if hasattr(request, "model_dump"):
        data = request.model_dump()
    elif isinstance(request, dict):
        data = dict(request)
    else:
        return {"type": type(request).__name__}
    if "source_document" in data:
        document = data.get("source_document")
        if isinstance(document, dict):
            data["source_document"] = {
                "source_id": document.get("source_id"),
                "source_file": document.get("source_file"),
                "source_type": document.get("source_type"),
                "content_chars": len(str(document.get("content") or "")),
            }
        else:
            data["source_document"] = "<omitted>"
    return {str(key): value for key, value in data.items() if value not in (None, [], {})}


def _format_request_lines(request: dict[str, object]) -> list[str]:
    if not request:
        return ["- No request metadata available."]
    lines: list[str] = []
    for key in sorted(request):
        value = request[key]
        if isinstance(value, dict):
            lines.append(f"- {key}: {_inline_mapping(value)}")
        else:
            lines.append(f"- {key}: {value}")
    return lines


def _inline_mapping(value: dict[str, object]) -> str:
    items = [f"{key}={item}" for key, item in value.items()]
    return ", ".join(items) if items else "{}"


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
