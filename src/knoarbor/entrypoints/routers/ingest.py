from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.schemas.ingest_run import UnifiedIngestRequest
from knoarbor.pipelines import IngestPipelineResult, IngestSourceResult
from knoarbor.services import ApplicationServices


def create_ingest_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/ingest", response_model=IngestPipelineResult | IngestSourceResult, tags=["ingest"])
    async def run_ingest(request: UnifiedIngestRequest) -> IngestPipelineResult | IngestSourceResult:
        return services.ingest.run_unified(request)

    return router
