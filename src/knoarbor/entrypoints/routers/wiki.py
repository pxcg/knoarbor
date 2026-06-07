from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.vaults import resolve_config_vault_path
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
        return service.list_pages(_resolve_vault_path(vault_path, vault_id, config_path))

    @router.get("/pages/content", response_model=WikiPageDetail)
    async def read_page(
        path: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiPageDetail:
        return service.read_page(_resolve_vault_path(vault_path, vault_id, config_path), path)

    @router.get("/pages/links", response_model=WikiPageBacklinksResponse)
    async def read_backlinks(
        path: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> WikiPageBacklinksResponse:
        return service.page_links(_resolve_vault_path(vault_path, vault_id, config_path), path)

    return router


def _resolve_vault_path(vault_path: str | None, vault_id: str | None, config_path: str | None) -> Path:
    config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
    return resolve_config_vault_path(config, vault_path=vault_path, vault_id=vault_id)
