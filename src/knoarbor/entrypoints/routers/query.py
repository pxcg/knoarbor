from __future__ import annotations

from fastapi import APIRouter, Query

from knoarbor.core.schemas.wiki_query import (
    WikiQueryFeedbackRequest,
    WikiQueryFeedbackResponse,
    WikiQueryTrendResponse,
    WikiSearchRequest,
    WikiSearchResponse,
)
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
        vault_path: str = Query(..., min_length=1),
        limit: int = Query(100, ge=1, le=1000),
    ) -> WikiQueryTrendResponse:
        return services.wiki_search.trend(vault_path, limit=limit)

    return router
