from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from knoarbor.runtime import vault_write_lock
from knoarbor.storage.vault_layout import maintenance_report_dir


def write_maintenance_report(vault_path: Path, report_kind: str, content: str, report_path: str | None = None) -> Path:
    """Write a user-readable maintenance report under the configured vault."""

    if report_path:
        output_path = _resolve_report_path(vault_path, report_kind, report_path)
        output_path.relative_to(vault_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_kind = re.sub(r"[^a-zA-Z0-9_-]+", "_", report_kind.strip().lower() or "custom").strip("_")
        output_path = maintenance_report_dir(vault_path, safe_kind) / f"{safe_kind}_report_{timestamp}.md"

    with vault_write_lock(vault_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
    return output_path


def _resolve_report_path(vault_path: Path, report_kind: str, report_path: str) -> Path:
    relative = Path(report_path.strip().replace("\\", "/").lstrip("/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Invalid report path: {report_path}")
    if relative.parts[:1] == ("maintenance",):
        filename = relative.name
        kind = _report_kind_from_filename(filename) or report_kind
        return (maintenance_report_dir(vault_path, kind) / filename).resolve()
    return (vault_path / relative).resolve()


def _report_kind_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem
    if stem.startswith("ingest_"):
        return "ingest"
    if stem.startswith("lint_") or stem.startswith("quality_"):
        return "lint"
    if stem.startswith("query_"):
        return "query"
    if stem.endswith("_run_report"):
        return "run-failure"
    return None
