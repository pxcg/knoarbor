from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.schemas.ingest_run import IngestRecoveryRunRequest, UnifiedIngestRequest
from knoarbor.core.schemas.run_monitor import RunStartResponse
from knoarbor.pipelines import IngestPipelineResult, IngestSourceResult
from knoarbor.services import ApplicationServices


def create_ingest_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/ingest", response_model=RunStartResponse | IngestPipelineResult | IngestSourceResult, tags=["ingest"])
    async def run_ingest(request: UnifiedIngestRequest) -> RunStartResponse | IngestPipelineResult | IngestSourceResult:
        if request.kind == "recovery":
            recovery_vault_path = request.recovery_vault_path or request.obsidian_vault_path
            recovery_run_id = request.recovery_of_run_id
            assert recovery_vault_path is not None
            assert recovery_run_id is not None
            return services.runs.start_ingest_recovery(
                recovery_vault_path,
                recovery_run_id,
                IngestRecoveryRunRequest(
                    config_path=request.config_path,
                    provider=request.provider,
                    max_tokens=request.max_tokens,
                    write=request.write,
                    write_report=request.write_report,
                    append_ledger=request.append_ledger,
                ),
                services.ingest.run,
                services.ingest.run_file,
            )
        if request.execution == "direct":
            return services.ingest.run_unified(request)
        if request.kind == "document":
            return services.runs.start_ingest_document(request.to_document_request(), services.ingest.run_document)
        if request.kind == "file":
            return services.runs.start_ingest_file(request.to_file_request(), services.ingest.run_file)
        return services.runs.start_ingest(request.to_connectors_request(), services.ingest.run)

    return router
