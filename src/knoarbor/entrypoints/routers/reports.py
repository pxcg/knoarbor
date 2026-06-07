from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.vaults import resolve_config_vault_path
from knoarbor.services.wiki_reports import WikiReportDetail, WikiReportService, WikiReportsResponse


def create_reports_router() -> APIRouter:
    router = APIRouter(prefix="/reports", tags=["reports"])
    service = WikiReportService()

    @router.get("", response_model=WikiReportsResponse)
    async def list_reports(
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiReportsResponse:
        return service.list_reports(_resolve_vault_path(vault_path, vault_id, config_path))

    @router.get("/content", response_model=WikiReportDetail)
    async def read_report(
        path: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiReportDetail:
        return service.read_report(_resolve_vault_path(vault_path, vault_id, config_path), path)

    return router


def _resolve_vault_path(vault_path: str | None, vault_id: str | None, config_path: str | None) -> Path:
    config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
    return resolve_config_vault_path(config, vault_path=vault_path, vault_id=vault_id)
