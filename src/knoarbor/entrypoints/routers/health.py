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
                        "CLI: knoarbor ingest",
                        "CLI: knoarbor ingest-document",
                        "/ingest/run",
                        "/ingest/document",
                    ],
                },
                "lint": {
                    "primary": [
                        "CLI: knoarbor lint-run",
                        "/lint/run",
                    ],
                },
                "query": ["CLI: knoarbor query", "/query/search"],
                "diagnostics": ["CLI: knoarbor doctor", "/doctor"],
                "ui": ["/", "/ui", "/ui/api/config", "/ui/api/status"],
            },
        }

    return router
