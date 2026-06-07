from __future__ import annotations

from fastapi import APIRouter, Query

from knoarbor.entrypoints.vault_selection import resolve_single_vault, resolve_vault_group
from knoarbor.services.wiki_reports import WikiReportDetail, WikiReportService, WikiReportsResponse


def create_reports_router() -> APIRouter:
    router = APIRouter(prefix="/reports", tags=["reports"])
    service = WikiReportService()

    @router.get("", response_model=WikiReportsResponse)
    async def list_reports(
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        vault_ids: list[str] = Query(default_factory=list),
        all_vaults: bool = Query(default=False),
        config_path: str | None = Query(default=None),
    ) -> WikiReportsResponse:
        vaults = resolve_vault_group(vault_path=vault_path, vault_id=vault_id, vault_ids=vault_ids, all_vaults=all_vaults, config_path=config_path)
        responses = [service.list_reports(vault.path, vault_id=vault.vault_id, vault_name=vault.vault_name) for vault in vaults]
        if len(responses) == 1:
            return responses[0]
        reports = sorted((report for response in responses for report in response.reports), key=lambda item: item.updated or "", reverse=True)
        return WikiReportsResponse(vault_path="", reports=reports)

    @router.get("/content", response_model=WikiReportDetail)
    async def read_report(
        path: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiReportDetail:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return service.read_report(vault.path, path, vault_id=vault.vault_id, vault_name=vault.vault_name)

    return router
