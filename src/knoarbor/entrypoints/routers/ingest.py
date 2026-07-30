from __future__ import annotations

import asyncio

from fastapi import APIRouter

from knoarbor.core.schemas.execution import WorkflowResponse
from knoarbor.core.schemas.ingest_run import UnifiedIngestRequest
from knoarbor.core.vault_selection import resolve_single_vault
from knoarbor.services import ApplicationServices
from knoarbor.core.schemas.run_monitor import TERMINAL_RUN_STATUSES


def create_ingest_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()
    coordinator = services.ingest_coordinator

    @router.post("/ingest", response_model=WorkflowResponse, tags=["ingest"])
    async def run_ingest(request: UnifiedIngestRequest) -> WorkflowResponse:
        started = coordinator.start(request)
        if request.execution == "queued":
            return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)
        vault = resolve_single_vault(request.recovery_vault_path or request.vault_path, request.vault_id, request.config_path)
        record = started.run
        while record.status not in TERMINAL_RUN_STATUSES:
            await asyncio.sleep(0.05)
            record = services.runs.read(str(vault.path), started.run_id, vault_id=vault.vault_id, vault_name=vault.vault_name)
        return WorkflowResponse(
            flow="ingest",
            execution="direct",
            status=record.status,
            run_id=record.run_id,
            run=record,
            result=record.result_summary,
        )

    return router
