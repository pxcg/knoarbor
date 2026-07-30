from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from knoarbor.core.errors import RunNotFound, error_info
from knoarbor.core.schemas.run_monitor import RunEventsResponse, RunListResponse, RunRecord, RunStartResponse, TERMINAL_RUN_STATUSES
from knoarbor.core.schemas.ingest_run import IngestRecoveryRunRequest
from knoarbor.core.schemas.ingest_control import (
    MaterializationRebuildRequest,
    MaterializationRebuildResponse,
    IngestControlResponse,
    IngestQueueResponse,
    IngestQueueTask,
)
from knoarbor.core.vault_selection import resolve_single_vault, resolve_vault_group
from knoarbor.services import ApplicationServices
from knoarbor.runtime.ingest_control import read_ingest_control, set_ingest_paused


def create_runs_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()
    coordinator = services.ingest_coordinator

    @router.get("/runs", response_model=RunListResponse, tags=["runs"])
    async def list_run_records(
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        vault_ids: list[str] = Query(default_factory=list),
        all_vaults: bool = Query(default=False),
        config_path: str | None = Query(default=None),
        active_only: bool = False,
        limit: int = 50,
    ) -> RunListResponse:
        vaults = resolve_vault_group(
            vault_path=vault_path, vault_id=vault_id, vault_ids=vault_ids, all_vaults=all_vaults, config_path=config_path
        )
        responses = [
            services.runs.list(str(vault.path), active_only=active_only, limit=limit, vault_id=vault.vault_id, vault_name=vault.vault_name)
            for vault in vaults
        ]
        runs = sorted((run for response in responses for run in response.runs), key=lambda item: item.updated_at, reverse=True)[:limit]
        return RunListResponse(runs=runs)

    @router.get("/runs/{run_id}", response_model=RunRecord, tags=["runs"])
    async def get_run(
        run_id: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> RunRecord:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return services.runs.read(str(vault.path), run_id, vault_id=vault.vault_id, vault_name=vault.vault_name)

    @router.get("/runs/{run_id}/events", response_model=RunEventsResponse, tags=["runs"])
    async def get_run_events(
        run_id: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
        after: int = 0,
        limit: int = 200,
    ) -> RunEventsResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return services.runs.events(str(vault.path), run_id, after=after, limit=limit)

    @router.get("/runs/{run_id}/stream", tags=["runs"])
    async def stream_run_events(
        run_id: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
        after: int = 0,
    ) -> StreamingResponse:
        resolved_vault_path = str(resolve_single_vault(vault_path, vault_id, config_path).path)

        async def _stream():
            cursor = after
            while True:
                events = services.runs.events(resolved_vault_path, run_id, after=cursor, limit=50).events
                for event in events:
                    cursor = max(cursor, event.sequence)
                    yield f"event: run_event\ndata: {event.model_dump_json()}\n\n"
                try:
                    record = services.runs.read(resolved_vault_path, run_id)
                    yield f"event: run_state\ndata: {record.model_dump_json()}\n\n"
                    if record.status in TERMINAL_RUN_STATUSES:
                        break
                except RunNotFound as exc:
                    info = error_info(exc)
                    info.pop("http_status", None)
                    yield f"event: error\ndata: {json.dumps({'error': info})}\n\n"
                    break
                await asyncio.sleep(2)

        return StreamingResponse(_stream(), media_type="text/event-stream")

    @router.post("/runs/{run_id}/cancel", response_model=RunRecord, tags=["runs"])
    async def cancel_run(
        run_id: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> RunRecord:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return services.runs.cancel(str(vault.path), run_id, vault_id=vault.vault_id, vault_name=vault.vault_name)

    @router.get("/ingest/control", tags=["ingest"])
    async def get_ingest_control(
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> IngestControlResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return IngestControlResponse.model_validate(read_ingest_control(vault.path))

    @router.post("/ingest/control/pause", tags=["ingest"])
    async def pause_ingest_control(
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> IngestControlResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return IngestControlResponse.model_validate(set_ingest_paused(vault.path, True))

    @router.post("/ingest/control/resume", tags=["ingest"])
    async def resume_ingest_control(
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> IngestControlResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        response = IngestControlResponse.model_validate(set_ingest_paused(vault.path, False))
        coordinator.resume_queued(vault.path)
        return response

    @router.get("/ingest/queue", response_model=IngestQueueResponse, tags=["ingest"])
    async def get_ingest_queue(
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> IngestQueueResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return services.runs.ingest_queue(str(vault.path))

    @router.post("/ingest/tasks/{task_id}/recover", response_model=RunStartResponse, tags=["ingest"])
    @router.post("/ingest/tasks/{task_id}/retry", response_model=RunStartResponse, tags=["ingest"])
    async def recover_ingest_task(
        task_id: str,
        request: IngestRecoveryRunRequest,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> RunStartResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return coordinator.recover_task(
            str(vault.path),
            task_id,
            request,
            vault_id=vault.vault_id,
        )

    @router.post("/ingest/tasks/{task_id}/cancel", response_model=IngestQueueTask, tags=["ingest"])
    async def cancel_ingest_task(
        task_id: str,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> IngestQueueTask:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return services.runs.cancel_ingest_task(str(vault.path), task_id)

    @router.post("/ingest/materialization/rebuild", response_model=MaterializationRebuildResponse, tags=["ingest"])
    async def rebuild_ingest_materialization(
        request: MaterializationRebuildRequest,
        vault_path: str | None = Query(default=None),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
    ) -> MaterializationRebuildResponse:
        vault = resolve_single_vault(vault_path, vault_id, config_path)
        return coordinator.rebuild_materialization(str(vault.path))

    return router
