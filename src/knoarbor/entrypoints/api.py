from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from knoarbor import __version__
from knoarbor.core.errors import KnoArborError
from knoarbor.entrypoints.errors import (
    file_not_found_handler,
    http_exception_handler,
    knoarbor_error_handler,
    request_validation_error_handler,
    unexpected_exception_handler,
    value_error_handler,
)
from knoarbor.entrypoints.routers import (
    create_chat_router,
    create_doctor_router,
    create_health_router,
    create_ingest_router,
    create_lint_router,
    create_models_router,
    create_query_router,
    create_reports_router,
    create_runtime_router,
    create_runs_router,
    create_sources_router,
    create_ui_router,
    create_vaults_router,
    create_wiki_router,
)
from knoarbor.services import ApplicationServices


def create_app(services: ApplicationServices | None = None) -> FastAPI:
    app = FastAPI(title="KnoArbor Processing Service", version=__version__)
    services = services or ApplicationServices()
    app.add_exception_handler(KnoArborError, knoarbor_error_handler)
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(FileNotFoundError, file_not_found_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
    app.include_router(create_chat_router(services))
    app.include_router(create_doctor_router(services))
    app.include_router(create_health_router())
    app.include_router(create_ingest_router(services))
    app.include_router(create_lint_router(services))
    app.include_router(create_models_router(services))
    app.include_router(create_query_router(services))
    app.include_router(create_reports_router(services))
    app.include_router(create_runtime_router())
    app.include_router(create_runs_router(services))
    app.include_router(create_sources_router(services))
    app.include_router(create_vaults_router(services))
    app.include_router(create_wiki_router(services))
    app.include_router(create_ui_router(include_static=os.environ.get("KNOARBOR_DESKTOP") != "1"))
    return app
