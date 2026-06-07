from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.schemas.wiki_query import (
    WikiQueryFeedbackRequest,
    WikiQueryFeedbackResponse,
    WikiQueryTrendResponse,
    WikiSearchRequest,
    WikiSearchResponse,
)
from knoarbor.core.vaults import resolve_config_vault_path
from knoarbor.services import ApplicationServices


def create_query_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/query", response_model=WikiSearchResponse, tags=["query"])
    async def search_query(request: WikiSearchRequest) -> WikiSearchResponse:
        effective_request = request if request.caller is not None else request.model_copy(update={"caller": "api"})
        return services.wiki_search.search(effective_request)

    @router.post("/query/feedback", response_model=WikiQueryFeedbackResponse, tags=["query"])
    async def record_query_feedback(request: WikiQueryFeedbackRequest) -> WikiQueryFeedbackResponse:
        effective_request = request if request.caller is not None else request.model_copy(update={"caller": "api"})
        return services.wiki_search.feedback(effective_request)

    @router.get("/query/trends", response_model=WikiQueryTrendResponse, tags=["query"])
    async def read_query_trends(
        vault_path: str | None = Query(default=None, min_length=1),
        vault_id: str | None = Query(default=None),
        config_path: str | None = Query(default=None),
        limit: int = Query(100, ge=1, le=1000),
    ) -> WikiQueryTrendResponse:
        config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
        return services.wiki_search.trend(str(resolve_config_vault_path(config, vault_path=vault_path, vault_id=vault_id)), limit=limit)

    return router
