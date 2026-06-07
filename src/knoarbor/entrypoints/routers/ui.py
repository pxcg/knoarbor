from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from knoarbor.audit.token_ledger import read_token_analysis
from knoarbor.services.ui_config import UiConfigService, summarize_default_config
from knoarbor.services.ui_config_models import (
    UiConfigDiagnostics,
    UiConfigFormResponse,
    UiConfigFormUpdateRequest,
    UiConfigResponse,
    UiConfigUpdateRequest,
    UiConfigUpdateResponse,
)
from knoarbor.services.wiki_graph import WikiGraph, build_wiki_graph
from knoarbor.storage.wiki_index import ensure_machine_index, machine_index_dir


class UiStatusResponse(BaseModel):
    vault_path: str
    pages: int
    raw_sources: int
    issues: int
    errors: int
    warnings: int
    info: int
    directories: dict[str, int] = Field(default_factory=dict)


class UiProjectDoc(BaseModel):
    path: str
    content: str


def create_ui_router() -> APIRouter:
    router = APIRouter()
    config_service = UiConfigService()

    @router.get("/", include_in_schema=False)
    async def root_index() -> FileResponse:
        return _ui_index_response()

    @router.get("/ui", tags=["ui"])
    async def ui_index() -> FileResponse:
        return _ui_index_response()

    @router.get("/ui/assets/{asset_path:path}", tags=["ui"])
    async def ui_asset(asset_path: str) -> FileResponse:
        asset = _resolve_ui_asset(f"assets/{asset_path}")
        return _ui_asset_response(asset)

    @router.get("/ui/api/config", response_model=UiConfigResponse, tags=["ui"])
    async def read_ui_config(config_path: str | None = Query(default=None)) -> UiConfigResponse:
        return config_service.read_raw(config_path)

    @router.put("/ui/api/config", response_model=UiConfigUpdateResponse, tags=["ui"])
    async def write_ui_config(request: UiConfigUpdateRequest) -> UiConfigUpdateResponse:
        return config_service.write_raw(request)

    @router.get("/ui/api/config/form", response_model=UiConfigFormResponse, tags=["ui"])
    async def read_ui_config_form(config_path: str | None = Query(default=None)) -> UiConfigFormResponse:
        return config_service.read_form(config_path)

    @router.put("/ui/api/config/form", response_model=UiConfigUpdateResponse, tags=["ui"])
    async def write_ui_config_form(request: UiConfigFormUpdateRequest) -> UiConfigUpdateResponse:
        return config_service.write_form(request)

    @router.get("/ui/api/config/diagnostics", response_model=UiConfigDiagnostics, tags=["ui"])
    async def read_ui_config_diagnostics(
        config_path: str | None = Query(default=None),
        refresh_source_counts: bool = Query(default=False),
    ) -> UiConfigDiagnostics:
        return config_service.read_diagnostics(config_path, refresh_source_counts=refresh_source_counts)

    @router.get("/ui/api/status", response_model=UiStatusResponse, tags=["ui"])
    async def read_ui_status(vault_path: str | None = Query(default=None)) -> UiStatusResponse:
        path = Path(vault_path or _summary_from_default_config().get("vault_path") or "./wiki").expanduser().resolve()
        index_pages = _read_machine_page_records(path)
        directories: dict[str, int] = {}
        for page in index_pages:
            directory = str(page.get("directory") or "unknown")
            directories[directory] = directories.get(directory, 0) + 1
        issue_counts = _latest_lint_issue_counts(path)
        return UiStatusResponse(
            vault_path=str(path),
            pages=len(index_pages),
            raw_sources=_count_raw_sources(path),
            issues=issue_counts["issues"],
            errors=issue_counts["errors"],
            warnings=issue_counts["warnings"],
            info=issue_counts["info"],
            directories=directories,
        )

    @router.get("/ui/api/graph", response_model=WikiGraph, tags=["ui"])
    async def read_ui_graph(vault_path: str | None = Query(default=None)) -> WikiGraph:
        path = Path(vault_path or _summary_from_default_config().get("vault_path") or "./wiki").expanduser().resolve()
        return build_wiki_graph(path)

    @router.get("/ui/api/tokens", tags=["ui"])
    async def read_ui_tokens(vault_path: str | None = Query(default=None), limit: int = Query(default=5000, ge=1, le=50000)) -> dict[str, object]:
        return read_token_analysis(_resolve_vault_path(vault_path), limit=limit)

    @router.get("/ui/api/docs/{doc_path:path}", response_model=UiProjectDoc, tags=["ui"])
    async def read_ui_doc(doc_path: str) -> UiProjectDoc:
        doc = _resolve_project_doc(doc_path)
        return UiProjectDoc(path=doc.relative_to(_project_docs_root()).as_posix(), content=doc.read_text(encoding="utf-8"))

    @router.get("/ui/{asset_path:path}", tags=["ui"])
    async def ui_root_asset(asset_path: str) -> FileResponse:
        asset = _resolve_ui_asset(asset_path)
        return _ui_asset_response(asset)

    return router


def _ui_index_response() -> FileResponse:
    response = FileResponse(_resolve_ui_asset("index.html"), media_type="text/html; charset=utf-8")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


def _ui_asset_response(asset: Path) -> FileResponse:
    if asset.suffix.lower() == ".html":
        response = FileResponse(asset, media_type="text/html; charset=utf-8")
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
    if "/assets/" in asset.as_posix():
        response = FileResponse(asset)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
    response = FileResponse(asset)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


def _resolve_ui_asset(name: str) -> Path:
    ui_root = Path(__file__).resolve().parents[2] / "ui" / "dist"
    asset_path = (ui_root / name).resolve()
    try:
        asset_path.relative_to(ui_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown UI asset") from exc
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="UI build asset is missing. Run `npm run build` in web/ first.")
    return asset_path


def _resolve_project_doc(name: str) -> Path:
    docs_root = _project_docs_root()
    doc_path = (docs_root / name).resolve()
    try:
        doc_path.relative_to(docs_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown project document") from exc
    if not doc_path.exists() or not doc_path.is_file() or doc_path.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail="Project document not found")
    return doc_path


def _project_docs_root() -> Path:
    return Path(__file__).resolve().parents[4] / "docs"


def _summary_from_default_config() -> dict[str, object]:
    return summarize_default_config()


def _count_raw_sources(vault_path: Path) -> int:
    raw_path = vault_path / "raw"
    if not raw_path.exists():
        return 0
    return sum(1 for path in raw_path.rglob("*") if path.is_file() and path.name != ".gitkeep")


def _read_machine_page_records(vault_path: Path) -> list[dict[str, object]]:
    if not vault_path.exists():
        return []
    ensure_machine_index(vault_path)
    pages_path = machine_index_dir(vault_path) / "pages.json"
    if not pages_path.exists():
        return []
    try:
        payload = json.loads(pages_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    pages = payload.get("pages", [])
    if not isinstance(pages, list):
        return []
    return [page for page in pages if isinstance(page, dict)]


def _latest_lint_issue_counts(vault_path: Path) -> dict[str, int]:
    latest = _latest_lint_report(vault_path)
    if latest is None:
        return {"issues": 0, "errors": 0, "warnings": 0, "info": 0}
    try:
        content = latest.read_text(encoding="utf-8")
    except OSError:
        return {"issues": 0, "errors": 0, "warnings": 0, "info": 0}

    deterministic_section = _markdown_section(content, "Deterministic Issues")
    section_errors = len(re.findall(r"^- \[error\]", deterministic_section, flags=re.MULTILINE))
    section_warnings = len(re.findall(r"^- \[warning\]", deterministic_section, flags=re.MULTILINE))
    section_info = len(re.findall(r"^- \[info\]", deterministic_section, flags=re.MULTILINE))
    section_total = section_errors + section_warnings + section_info
    if section_total:
        return {"issues": section_total, "errors": section_errors, "warnings": section_warnings, "info": section_info}

    issues = _report_int(content, "deterministic_issues")
    if issues is None:
        issues = _report_int(content, "issues") or 0
    return {
        "issues": issues,
        "errors": _report_int(content, "errors") or 0,
        "warnings": _report_int(content, "warnings") or 0,
        "info": _report_int(content, "info") or 0,
    }


def _latest_lint_report(vault_path: Path) -> Path | None:
    maintenance_path = vault_path / "maintenance"
    if not maintenance_path.exists():
        return None
    candidates = list(maintenance_path.glob("lint_run_report_*.md")) + list(maintenance_path.glob("lint_report_*.md"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _report_int(content: str, key: str) -> int | None:
    escaped = re.escape(key)
    match = re.search(rf"^- {escaped}:\s*(\d+)\s*$", content, flags=re.MULTILINE)
    if not match:
        return None
    return int(match.group(1))


def _markdown_section(content: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$"
    match = re.search(pattern, content, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", content[start:], flags=re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(content)
    return content[start:end]


def _resolve_vault_path(vault_path: str | None) -> Path:
    return Path(vault_path or _summary_from_default_config().get("vault_path") or "./wiki").expanduser().resolve()


def _resolve_vault_file(vault_path: Path, relative_path: str) -> Path:
    page_path = (vault_path / relative_path).resolve()
    try:
        page_path.relative_to(vault_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path must stay inside the configured vault") from exc
    if not page_path.exists() or not page_path.is_file():
        raise HTTPException(status_code=404, detail=f"Vault file not found: {relative_path}")
    return page_path
