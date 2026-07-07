from __future__ import annotations

from fastapi import APIRouter, Query

from knoarbor.core.schemas.image_generation import ImageProvidersResponse
from knoarbor.core.schemas.model_probe import (
    ModelApplyCapabilitiesRequest,
    ModelApplyCapabilitiesResponse,
    ModelDiscoveryRequest,
    ModelDiscoveryResponse,
    ModelProvidersResponse,
)
from knoarbor.services import ApplicationServices


def create_models_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter(prefix="/models", tags=["models"])

    @router.get("/providers", response_model=ModelProvidersResponse)
    async def list_model_providers(
        config_path: str | None = Query(default=None),
    ) -> ModelProvidersResponse:
        return services.model_probe.providers(config_path=config_path)

    @router.get("/image-providers", response_model=ImageProvidersResponse)
    async def list_image_model_providers(
        config_path: str | None = Query(default=None),
    ) -> ImageProvidersResponse:
        return services.image_generation.providers(config_path=config_path)

    @router.post("/discover", response_model=ModelDiscoveryResponse)
    async def discover_model_provider(request: ModelDiscoveryRequest) -> ModelDiscoveryResponse:
        return services.model_probe.discover(request)

    @router.post("/apply-capabilities", response_model=ModelApplyCapabilitiesResponse)
    async def apply_model_capabilities(
        request: ModelApplyCapabilitiesRequest,
    ) -> ModelApplyCapabilitiesResponse:
        return services.model_probe.apply_capabilities(request)

    return router
