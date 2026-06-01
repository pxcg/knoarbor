from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import RunNotFound, error_info
from knoarbor.core.schemas.run_monitor import RunEventsResponse, RunListResponse, RunRecord, TERMINAL_RUN_STATUSES
from knoarbor.services import ApplicationServices


def create_runs_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.get("/runs", response_model=RunListResponse, tags=["runs"])
    async def list_run_records(
        vault_path: str | None = Query(default=None),
        active_only: bool = False,
        limit: int = 50,
    ) -> RunListResponse:
        return services.runs.list(str(_resolve_vault_path(vault_path)), active_only=active_only, limit=limit)

    @router.get("/runs/{run_id}", response_model=RunRecord, tags=["runs"])
    async def get_run(run_id: str, vault_path: str | None = Query(default=None)) -> RunRecord:
        return services.runs.read(str(_resolve_vault_path(vault_path)), run_id)

    @router.get("/runs/{run_id}/events", response_model=RunEventsResponse, tags=["runs"])
    async def get_run_events(
        run_id: str,
        vault_path: str | None = Query(default=None),
        after: int = 0,
        limit: int = 200,
    ) -> RunEventsResponse:
        return services.runs.events(str(_resolve_vault_path(vault_path)), run_id, after=after, limit=limit)

    @router.get("/runs/{run_id}/stream", tags=["runs"])
    async def stream_run_events(
        run_id: str,
        vault_path: str | None = Query(default=None),
        after: int = 0,
    ) -> StreamingResponse:
        resolved_vault_path = str(_resolve_vault_path(vault_path))

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
    async def cancel_run(run_id: str, vault_path: str | None = Query(default=None)) -> RunRecord:
        return services.runs.cancel(str(_resolve_vault_path(vault_path)), run_id)

    return router


def _resolve_vault_path(vault_path: str | None) -> Path:
    if vault_path:
        return Path(vault_path).expanduser().resolve()
    config = load_config(default_config_path())
    return config.vault.path.expanduser().resolve()
