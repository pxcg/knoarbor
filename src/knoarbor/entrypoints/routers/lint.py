from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.schemas.execution import WorkflowResponse
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.services import ApplicationServices


def create_lint_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/lint", response_model=WorkflowResponse, tags=["lint"])
    async def run_lint(request: LintRunRequest) -> WorkflowResponse:
        if request.execution == "direct":
            result = services.wiki_linter.run_maintenance(request)
            return WorkflowResponse(
                flow="lint",
                execution="direct",
                status="completed",
                result=result.model_dump(mode="json"),
            )
        started = services.runs.start_lint(request, services.wiki_linter.run_maintenance)
        return WorkflowResponse(flow="lint", execution="queued", status=started.status, run_id=started.run_id, run=started.run)

    return router
