from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.schemas.execution import WorkflowResponse
from knoarbor.core.schemas.ingest_run import IngestRecoveryRunRequest, UnifiedIngestRequest
from knoarbor.core.vault_selection import resolve_single_vault
from knoarbor.services import ApplicationServices


def create_ingest_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/ingest", response_model=WorkflowResponse, tags=["ingest"])
    async def run_ingest(request: UnifiedIngestRequest) -> WorkflowResponse:
        if request.kind == "recovery":
            recovery_vault = resolve_single_vault(request.recovery_vault_path or request.vault_path, request.vault_id, request.config_path)
            recovery_run_id = request.recovery_of_run_id
            assert recovery_run_id is not None
            started = services.runs.start_ingest_recovery(
                str(recovery_vault.path),
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
                services.ingest.run_folder,
            )
            return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)
        if request.execution == "direct":
            result = services.ingest.run_unified(request)
            return WorkflowResponse(
                flow="ingest",
                execution="direct",
                status="completed",
                result=result.model_dump(mode="json"),
            )
        if request.kind == "document":
            started = services.runs.start_ingest_document(request.to_document_request(), services.ingest.run_document)
            return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)
        if request.kind == "excerpt":
            started = services.runs.start_ingest_document(request.to_excerpt_request(), services.ingest.run_document)
            return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)
        if request.kind == "file":
            started = services.runs.start_ingest_file(request.to_file_request(), services.ingest.run_file)
            return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)
        if request.kind == "folder":
            started = services.runs.start_ingest_folder(request.to_folder_request(), services.ingest.run_folder)
            return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)
        started = services.runs.start_ingest(request.to_connectors_request(), services.ingest.run)
        return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)

    return router
