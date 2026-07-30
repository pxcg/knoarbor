from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from knoarbor.core.schemas.chat import (
    ChatCitationResolveRequest,
    ChatCitationResolveResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionCloseRequest,
    ChatSessionDeleteResponse,
    ChatSessionIngestRequest,
    ChatSessionListResponse,
    ChatSessionMutationRequest,
    ChatSessionRecord,
    ChatSessionRetryRequest,
    ChatSessionUpdateRequest,
    ChatSessionWorkflowResponse,
)
from knoarbor.core.vault_selection import resolve_single_vault
from knoarbor.core.schemas.execution import WorkflowResponse
from knoarbor.services.chat_context import session_target
from knoarbor.services.chat_session_workflow import (
    close_chat_session_workflow,
    retry_chat_session_turn as retry_chat_session_turn_workflow,
    start_chat_session_ingest,
)
from knoarbor.services.chat_stream import chat_event_stream
from knoarbor.services import ApplicationServices


def create_chat_router(services: ApplicationServices) -> APIRouter:
    router = APIRouter(tags=["chat"])

    @router.post("/chat", response_model=ChatResponse)
    async def run_chat(request: ChatRequest) -> ChatResponse:
        return services.chat.chat(request, services)

    @router.post("/chat/stream")
    async def stream_chat(request: ChatRequest) -> StreamingResponse:
        return StreamingResponse(
            chat_event_stream(request, services),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/chat/citations/resolve", response_model=ChatCitationResolveResponse)
    async def resolve_chat_citations(
        request: ChatCitationResolveRequest,
    ) -> ChatCitationResolveResponse:
        vault = resolve_single_vault(
            request.vault_path,
            request.vault_id,
            request.config_path,
        )
        return services.chat_citations.resolve(vault.path, request.citations)

    @router.get("/chat/sessions", response_model=ChatSessionListResponse)
    async def list_chat_sessions(
        config_path: str | None = None,
        vault_path: str | None = None,
        vault_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ChatSessionListResponse:
        target = session_target(config_path=config_path, vault_path=vault_path, vault_id=vault_id)
        return services.chat_sessions.list_sessions(
            target.path,
            limit=limit,
            offset=offset,
            sessions_dir=target.sessions_dir,
        )

    @router.get("/chat/sessions/{session_id}", response_model=ChatSessionRecord)
    async def read_chat_session(
        session_id: str,
        config_path: str | None = None,
        vault_path: str | None = None,
        vault_id: str | None = None,
    ) -> ChatSessionRecord:
        target = session_target(config_path=config_path, vault_path=vault_path, vault_id=vault_id)
        return services.chat_sessions.read_session(target.path, session_id, sessions_dir=target.sessions_dir)

    @router.delete("/chat/sessions/{session_id}", response_model=ChatSessionDeleteResponse)
    async def delete_chat_session(
        session_id: str,
        request: ChatSessionMutationRequest,
    ) -> ChatSessionDeleteResponse:
        target = session_target(config_path=request.config_path, vault_path=request.vault_path, vault_id=request.vault_id)
        return ChatSessionDeleteResponse(
            deleted=services.chat_sessions.delete_session(
                target.path,
                session_id,
                request.expected_session_revision,
                sessions_dir=target.sessions_dir,
            ),
            session_id=session_id,
        )

    @router.delete("/chat/sessions/{session_id}/turns/{turn_id}", response_model=ChatSessionRecord)
    async def delete_chat_turn(
        session_id: str,
        turn_id: str,
        request: ChatSessionMutationRequest,
    ) -> ChatSessionRecord:
        target = session_target(config_path=request.config_path, vault_path=request.vault_path, vault_id=request.vault_id)
        return services.chat_sessions.remove_turn(
            target.path,
            session_id,
            turn_id,
            request.expected_session_revision,
            sessions_dir=target.sessions_dir,
        )

    @router.patch("/chat/sessions/{session_id}", response_model=ChatSessionRecord)
    async def update_chat_session(
        session_id: str,
        request: ChatSessionUpdateRequest,
    ) -> ChatSessionRecord:
        target = session_target(
            config_path=request.config_path,
            vault_path=request.vault_path,
            vault_id=request.vault_id,
        )
        return services.chat_sessions.update_title(
            target.path,
            session_id,
            request.title,
            request.expected_session_revision,
            sessions_dir=target.sessions_dir,
        )

    @router.post("/chat/sessions/{session_id}/ingest", response_model=WorkflowResponse)
    async def ingest_chat_session(
        session_id: str,
        request: ChatSessionIngestRequest,
    ) -> WorkflowResponse:
        started = start_chat_session_ingest(services, session_id, request)
        return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)

    @router.post("/chat/sessions/{session_id}/close", response_model=ChatSessionWorkflowResponse)
    async def close_chat_session(
        session_id: str,
        request: ChatSessionCloseRequest,
    ) -> ChatSessionWorkflowResponse:
        return close_chat_session_workflow(services, session_id, request)

    @router.post("/chat/sessions/{session_id}/retry", response_model=ChatResponse)
    async def retry_chat_session_turn(
        session_id: str,
        request: ChatSessionRetryRequest,
    ) -> ChatResponse:
        return retry_chat_session_turn_workflow(services, session_id, request)

    return router
