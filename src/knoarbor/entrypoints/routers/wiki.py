from __future__ import annotations

from fastapi import APIRouter, Body, Query

from knoarbor.core.vault_selection import resolve_single_vault
from knoarbor.core.schemas.projection_edit import ProjectionEdit
from knoarbor.core.schemas.raw_revision_edit import RawRevisionEdit
from knoarbor.core.schemas.execution import WorkflowResponse
from knoarbor.services import ApplicationServices
from knoarbor.services.raw_revision_edits import build_raw_revision_ingest_request
from knoarbor.services.wiki_pages import WikiPageDeleteResponse, WikiPageDetail, WikiPageRelationsResponse, WikiPagesResponse


def create_wiki_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter(prefix="/wiki", tags=["wiki"])
    service = services.wiki_pages

    @router.get("/pages", response_model=WikiPagesResponse)
    async def list_pages(
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiPagesResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return service.list_pages(vault.path, vault_id=vault.vault_id, vault_name=vault.vault_name)

    @router.get("/pages/content", response_model=WikiPageDetail)
    async def read_page(
        path: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiPageDetail:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return service.read_page(vault.path, path, vault_id=vault.vault_id, vault_name=vault.vault_name)

    @router.get("/pages/relations", response_model=WikiPageRelationsResponse)
    async def read_page_relations(
        path: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiPageRelationsResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return service.page_relations(vault.path, path, vault_id=vault.vault_id, vault_name=vault.vault_name)

    @router.patch("/pages/content", response_model=WikiPageDetail)
    async def edit_page(
        path: str = Body(...),
        edit: ProjectionEdit = Body(...),
        vault_path: str | None = Body(default=None),
        vault_id: str | None = Body(default=None),
        config_path: str | None = Body(default=None),
    ) -> WikiPageDetail:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return service.edit_page(vault.path, path, edit, vault_id=vault.vault_id, vault_name=vault.vault_name)

    @router.delete("/pages/content", response_model=WikiPageDeleteResponse)
    async def delete_page(
        path: str = Body(...),
        vault_path: str | None = Body(default=None),
        vault_id: str | None = Body(default=None),
        config_path: str | None = Body(default=None),
    ) -> WikiPageDeleteResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return service.delete_page(vault.path, path)

    @router.patch("/pages/raw", response_model=WorkflowResponse)
    async def edit_raw_page(
        path: str = Body(...),
        edit: RawRevisionEdit = Body(...),
        vault_path: str | None = Body(default=None),
        vault_id: str | None = Body(default=None),
        config_path: str | None = Body(default=None),
    ) -> WorkflowResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        page = service.resolve_page_path(vault.path, path)
        request = build_raw_revision_ingest_request(
            vault.path,
            page,
            edit,
            config_path=config_path,
            vault_id=vault.vault_id,
        )
        started = services.ingest_coordinator.start(request)
        return WorkflowResponse(
            flow="ingest",
            execution="queued",
            status=started.status,
            run_id=started.run_id,
            run=started.run,
        )

    return router
