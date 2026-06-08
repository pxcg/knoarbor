from __future__ import annotations

from fastapi import APIRouter, Query

from knoarbor.core.schemas.connectors import SourceCatalogResponse
from knoarbor.services import ApplicationServices


def create_sources_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter(prefix="/sources", tags=["sources"])

    @router.get("", response_model=SourceCatalogResponse)
    async def list_source_catalog(
        config_path: str | None = Query(default=None),
        connector: list[str] | None = Query(default=None),
    ) -> SourceCatalogResponse:
        return services.source_catalog.list_catalog(
            config_path=config_path,
            connector_names=connector,
        )

    return router
