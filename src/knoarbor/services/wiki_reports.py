from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.core.errors import UserInputError, WikiPageNotFound
from knoarbor.core.markdown import compact_inline_text, extract_heading


class WikiReportSummary(BaseModel):
    path: str
    title: str
    kind: str
    updated: str | None = None
    size: int
    preview: str = ""


class WikiReportsResponse(BaseModel):
    vault_path: str
    reports: list[WikiReportSummary] = Field(default_factory=list)


class WikiReportDetail(BaseModel):
    path: str
    content: str
    summary: WikiReportSummary


class WikiReportService:
    def list_reports(self, vault_path: Path) -> WikiReportsResponse:
        vault = vault_path.expanduser().resolve()
        return WikiReportsResponse(vault_path=str(vault), reports=collect_report_summaries(vault))

    def read_report(self, vault_path: Path, path: str) -> WikiReportDetail:
        vault = vault_path.expanduser().resolve()
        report_path = resolve_report_path(vault, path)
        content = report_path.read_text(encoding="utf-8")
        summary = summarize_report(vault, report_path, content)
        return WikiReportDetail(path=summary.path, content=content, summary=summary)


def collect_report_summaries(vault_path: Path) -> list[WikiReportSummary]:
    maintenance_path = vault_path / "maintenance"
    if not maintenance_path.exists():
        return []
    reports: list[WikiReportSummary] = []
    for path in sorted(maintenance_path.glob("*report*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        content = path.read_text(encoding="utf-8")
        reports.append(summarize_report(vault_path, path, content))
    return reports


def resolve_report_path(vault_path: Path, relative_path: str) -> Path:
    report_path = (vault_path / relative_path).resolve()
    try:
        report_path.relative_to(vault_path.resolve())
    except ValueError as exc:
        raise UserInputError("Report path must stay inside the configured vault.") from exc
    if report_path.suffix.lower() != ".md":
        raise UserInputError("Only Markdown reports can be read.")
    if not report_path.exists() or not report_path.is_file():
        raise WikiPageNotFound(f"Report not found: {relative_path}")
    return report_path


def summarize_report(vault_path: Path, path: Path, content: str) -> WikiReportSummary:
    relative = path.relative_to(vault_path).as_posix()
    name = path.name.lower()
    if "lint" in name:
        kind = "lint"
    elif "quality" in name:
        kind = "quality"
    elif "ingest" in name:
        kind = "ingest"
    elif "query" in name:
        kind = "query"
    else:
        kind = "maintenance"
    return WikiReportSummary(
        path=relative,
        title=extract_heading(content, path.stem),
        kind=kind,
        updated=_mtime_iso(path),
        size=path.stat().st_size,
        preview=compact_inline_text(re.sub(r"\s+", " ", content), 280),
    )


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
