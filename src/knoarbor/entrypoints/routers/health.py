from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter


STARTED_AT = datetime.now()


def create_health_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, object]:
        now = datetime.now()
        return {
            "status": "ok",
            "service_role": "local_knowledge_core",
            "pid": os.getpid(),
            "started_at": STARTED_AT.strftime("%Y-%m-%d %H:%M:%S"),
            "uptime_seconds": int((now - STARTED_AT).total_seconds()),
            "phases": {
                "ingest": {
                    "primary": [
                        "CLI: knoar ingest",
                        "/ingest",
                    ],
                },
                "lint": {
                    "primary": [
                        "CLI: knoar lint",
                        "/lint",
                    ],
                },
                "query": ["CLI: knoar query", "/query"],
                "runs": ["GET /runs", "GET /runs/{run_id}", "POST /runs/{run_id}/cancel"],
                "diagnostics": ["CLI: knoar doctor", "/doctor"],
                "config": ["/config", "/config/form", "/config/diagnostics"],
                "desktop_renderer": ["/", "/ui"],
                "vault_status": ["/vaults/status", "/wiki/graph", "/tokens"],
            },
        }

    return router
