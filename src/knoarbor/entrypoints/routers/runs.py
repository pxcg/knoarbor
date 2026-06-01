from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from knoarbor.core.errors import RunNotFound, error_info
from knoarbor.core.schemas.run_monitor import RunEventsResponse, RunListResponse, RunRecord, RunStartResponse, TERMINAL_RUN_STATUSES
from knoarbor.core.schemas.run_start import RunStartRequest
from knoarbor.services import ApplicationServices


def create_runs_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/runs", response_model=RunStartResponse, tags=["runs"])
    async def start_run(request: RunStartRequest) -> RunStartResponse:
        return services.runs.start(
            request,
            ingest_runner=services.ingest.run,
            ingest_file_runner=services.ingest.run_file,
            ingest_document_runner=services.ingest.run_document,
            lint_runner=services.wiki_linter.run_maintenance,
            query_runner=services.wiki_search.search,
        )

    @router.get("/runs", response_model=RunListResponse, tags=["runs"])
    async def list_run_records(vault_path: str, active_only: bool = False, limit: int = 50) -> RunListResponse:
        return services.runs.list(vault_path, active_only=active_only, limit=limit)

    @router.get("/runs/{run_id}", response_model=RunRecord, tags=["runs"])
    async def get_run(vault_path: str, run_id: str) -> RunRecord:
        return services.runs.read(vault_path, run_id)

    @router.get("/runs/{run_id}/events", response_model=RunEventsResponse, tags=["runs"])
    async def get_run_events(vault_path: str, run_id: str, after: int = 0, limit: int = 200) -> RunEventsResponse:
        return services.runs.events(vault_path, run_id, after=after, limit=limit)

    @router.get("/runs/{run_id}/stream", tags=["runs"])
    async def stream_run_events(vault_path: str, run_id: str, after: int = 0) -> StreamingResponse:
        async def _stream():
            cursor = after
            while True:
                events = services.runs.events(vault_path, run_id, after=cursor, limit=50).events
                for event in events:
                    cursor = max(cursor, event.sequence)
                    yield f"event: run_event\ndata: {event.model_dump_json()}\n\n"
                try:
                    record = services.runs.read(vault_path, run_id)
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
    async def cancel_run(vault_path: str, run_id: str) -> RunRecord:
        return services.runs.cancel(vault_path, run_id)

    return router
