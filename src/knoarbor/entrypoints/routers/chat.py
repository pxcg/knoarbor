from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.schemas.chat import ChatRequest, ChatResponse, ChatSessionListResponse, ChatSessionRecord
from knoarbor.services.chat_context import session_target
from knoarbor.services import ApplicationServices


def create_chat_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter(tags=["chat"])

    @router.post("/chat", response_model=ChatResponse)
    async def run_chat(request: ChatRequest) -> ChatResponse:
        return services.chat.chat(request, services)

    @router.get("/chat/sessions", response_model=ChatSessionListResponse)
    async def list_chat_sessions(
        config_path: str | None = None,
        vault_path: str | None = None,
        vault_id: str | None = None,
        limit: int = 50,
    ) -> ChatSessionListResponse:
        target = session_target(ChatRequest(config_path=config_path, vault_path=vault_path, vault_id=vault_id, messages=[{"role": "user", "content": "list sessions"}]))
        return services.chat_sessions.list_sessions(target.path, limit=limit)

    @router.get("/chat/sessions/{session_id}", response_model=ChatSessionRecord)
    async def read_chat_session(
        session_id: str,
        config_path: str | None = None,
        vault_path: str | None = None,
        vault_id: str | None = None,
    ) -> ChatSessionRecord:
        target = session_target(ChatRequest(config_path=config_path, vault_path=vault_path, vault_id=vault_id, messages=[{"role": "user", "content": "read session"}]))
        return services.chat_sessions.read_session(target.path, session_id)

    return router
