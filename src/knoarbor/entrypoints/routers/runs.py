from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from knoarbor.core.errors import RunNotFound, error_info
from knoarbor.core.schemas.run_monitor import RunEventsResponse, RunListResponse, RunRecord, TERMINAL_RUN_STATUSES
from knoarbor.core.vault_selection import resolve_single_vault, resolve_vault_group
from knoarbor.services import ApplicationServices


def create_runs_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

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
        vaults = resolve_vault_group(vault_path=vault_path, vault_id=vault_id, vault_ids=vault_ids, all_vaults=all_vaults, config_path=config_path)
        responses = [services.runs.list(str(vault.path), active_only=active_only, limit=limit, vault_id=vault.vault_id, vault_name=vault.vault_name) for vault in vaults]
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

    return router
