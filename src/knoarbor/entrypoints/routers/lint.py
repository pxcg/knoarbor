from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.schemas.wiki_lint import (
    LintRunRequest,
    LintRunResult,
)
from knoarbor.services import ApplicationServices


def create_lint_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/lint/run", response_model=LintRunResult, tags=["lint"])
    async def run_lint(request: LintRunRequest) -> LintRunResult:
        return services.wiki_linter.run_maintenance(request)

    return router
