from __future__ import annotations

from fastapi import APIRouter, Query

from knoarbor.core.schemas.doctor import DoctorReport
from knoarbor.services import ApplicationServices


def create_doctor_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.get("/doctor", response_model=DoctorReport, tags=["diagnostics"])
    async def doctor(
        config_path: str | None = Query(default=None),
        connector: list[str] | None = Query(default=None),
        check_model_runtime: bool = Query(default=True),
        check_connector_runtime: bool = Query(default=True),
    ) -> DoctorReport:
        return services.doctor.run(
            config_path=config_path,
            connector_names=connector,
            check_model_runtime=check_model_runtime,
            check_connector_runtime=check_connector_runtime,
        )

    return router
