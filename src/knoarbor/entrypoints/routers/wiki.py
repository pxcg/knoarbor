from __future__ import annotations

from fastapi import APIRouter, Query

from knoarbor.entrypoints.vault_selection import resolve_single_vault
from knoarbor.services.wiki_pages import WikiPageBacklinksResponse, WikiPageDetail, WikiPageService, WikiPagesResponse


def create_wiki_router() -> APIRouter:
    router = APIRouter(prefix="/wiki", tags=["wiki"])
    service = WikiPageService()

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

    @router.get("/pages/links", response_model=WikiPageBacklinksResponse)
    async def read_backlinks(
        path: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiPageBacklinksResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return service.page_links(vault.path, path, vault_id=vault.vault_id, vault_name=vault.vault_name)

    return router
