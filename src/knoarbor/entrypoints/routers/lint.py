from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.schemas.run_monitor import RunStartResponse
from knoarbor.core.schemas.wiki_lint import LintRunRequest, LintRunResult
from knoarbor.services import ApplicationServices


def create_lint_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/lint", response_model=RunStartResponse | LintRunResult, tags=["lint"])
    async def run_lint(request: LintRunRequest) -> RunStartResponse | LintRunResult:
        if request.execution == "direct":
            return services.wiki_linter.run_maintenance(request)
        return services.runs.start_lint(request, services.wiki_linter.run_maintenance)

    return router
