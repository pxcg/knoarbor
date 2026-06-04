from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query

from knoarbor.core.config import default_config_path, load_config
from knoarbor.services.wiki_reports import WikiReportDetail, WikiReportService, WikiReportsResponse


def create_reports_router() -> APIRouter:
    router = APIRouter(prefix="/reports", tags=["reports"])
    service = WikiReportService()

    @router.get("", response_model=WikiReportsResponse)
    async def list_reports(vault_path: str | None = Query(default=None)) -> WikiReportsResponse:
        return service.list_reports(_resolve_vault_path(vault_path))

    @router.get("/content", response_model=WikiReportDetail)
    async def read_report(path: str, vault_path: str | None = Query(default=None)) -> WikiReportDetail:
        return service.read_report(_resolve_vault_path(vault_path), path)

    return router


def _resolve_vault_path(vault_path: str | None) -> Path:
    if vault_path:
        return Path(vault_path).expanduser().resolve()
    config = load_config(default_config_path())
    return config.vault.path.expanduser().resolve()
