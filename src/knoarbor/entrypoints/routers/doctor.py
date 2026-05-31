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
    ) -> DoctorReport:
        return services.doctor.run(config_path=config_path, connector_names=connector)

    return router
