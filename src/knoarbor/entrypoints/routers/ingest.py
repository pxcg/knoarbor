from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.schemas.ingest_run import IngestDocumentRunRequest, IngestFileRunRequest, IngestRunRequest
from knoarbor.pipelines import IngestPipelineResult, IngestSourceResult
from knoarbor.services import ApplicationServices


def create_ingest_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/ingest/run", response_model=IngestPipelineResult, tags=["ingest"])
    async def run_ingest(request: IngestRunRequest) -> IngestPipelineResult:
        return services.ingest.run(request)

    @router.post("/ingest/document", response_model=IngestSourceResult, tags=["ingest"])
    async def run_ingest_document(request: IngestDocumentRunRequest) -> IngestSourceResult:
        return services.ingest.run_document(request)

    @router.post("/ingest/file", response_model=IngestPipelineResult, tags=["ingest"])
    async def run_ingest_file(request: IngestFileRunRequest) -> IngestPipelineResult:
        return services.ingest.run_file(request)

    return router
