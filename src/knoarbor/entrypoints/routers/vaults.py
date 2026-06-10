from __future__ import annotations

from fastapi import APIRouter, Query

from knoarbor.core.schemas.vaults import VaultListResponse
from knoarbor.services import ApplicationServices


def create_vaults_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter(prefix="/vaults", tags=["vaults"])

    @router.get("", response_model=VaultListResponse)
    async def list_vaults(config_path: str | None = Query(default=None)) -> VaultListResponse:
        return services.vaults.list_vaults(config_path=config_path)

    return router
