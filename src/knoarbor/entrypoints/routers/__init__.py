from __future__ import annotations

from knoarbor.entrypoints.routers.doctor import create_doctor_router
from knoarbor.entrypoints.routers.health import create_health_router
from knoarbor.entrypoints.routers.ingest import create_ingest_router
from knoarbor.entrypoints.routers.lint import create_lint_router
from knoarbor.entrypoints.routers.models import create_models_router
from knoarbor.entrypoints.routers.query import create_query_router
from knoarbor.entrypoints.routers.reports import create_reports_router
from knoarbor.entrypoints.routers.runtime import create_runtime_router
from knoarbor.entrypoints.routers.runs import create_runs_router
from knoarbor.entrypoints.routers.sources import create_sources_router
from knoarbor.entrypoints.routers.ui import create_ui_router
from knoarbor.entrypoints.routers.wiki import create_wiki_router

__all__ = [
    "create_doctor_router",
    "create_health_router",
    "create_ingest_router",
    "create_lint_router",
    "create_models_router",
    "create_query_router",
    "create_reports_router",
    "create_runtime_router",
    "create_runs_router",
    "create_sources_router",
    "create_ui_router",
    "create_wiki_router",
]
