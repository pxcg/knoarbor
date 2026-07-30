from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

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
from knoarbor.product import PRODUCT, product_env
from knoarbor.services import ApplicationServices
from knoarbor.core.config import default_config_path, load_config
from knoarbor.services.startup_reconciler import StartupReconciler


def create_app(services: ApplicationServices | None = None, *, config_path: str | Path | None = None) -> FastAPI:
    services = services or ApplicationServices()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
        reconciler = StartupReconciler(services.ingest_coordinator)
        for profile in config.vaults.profiles.values():
            reconciler.reconcile(profile.path)
        try:
            yield
        finally:
            services.operations.shutdown()

    app = FastAPI(title=PRODUCT.service_title, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"{PRODUCT.renderer_scheme}://{PRODUCT.renderer_host}"],
        allow_methods=["POST"],
        allow_headers=["content-type"],
    )
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
    include_static_ui = product_env("DESKTOP") != "1"
    app.include_router(create_ui_router(include_static=include_static_ui))
    return app
