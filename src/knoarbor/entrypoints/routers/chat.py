from __future__ import annotations

from fastapi import APIRouter

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSessionCloseRequest,
    ChatSessionDeleteResponse,
    ChatSessionIngestRequest,
    ChatSessionListResponse,
    ChatSessionRecord,
    ChatSessionRetryRequest,
    ChatSessionWorkflowResponse,
)
from knoarbor.core.schemas.execution import WorkflowResponse
from knoarbor.core.schemas.ingest_run import IngestDocumentRunRequest
from knoarbor.core.vaults import select_config_vault
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

    @router.delete("/chat/sessions/{session_id}", response_model=ChatSessionDeleteResponse)
    async def delete_chat_session(
        session_id: str,
        config_path: str | None = None,
        vault_path: str | None = None,
        vault_id: str | None = None,
    ) -> ChatSessionDeleteResponse:
        target = session_target(ChatRequest(config_path=config_path, vault_path=vault_path, vault_id=vault_id, messages=[{"role": "user", "content": "delete session"}]))
        return ChatSessionDeleteResponse(deleted=services.chat_sessions.delete_session(target.path, session_id), session_id=session_id)

    @router.post("/chat/sessions/{session_id}/ingest", response_model=WorkflowResponse)
    async def ingest_chat_session(
        session_id: str,
        request: ChatSessionIngestRequest | None = None,
    ) -> WorkflowResponse:
        request = request or ChatSessionIngestRequest()
        started = _start_chat_session_ingest(services, session_id, request)
        return WorkflowResponse(flow="ingest", execution="queued", status=started.status, run_id=started.run_id, run=started.run)

    @router.post("/chat/sessions/{session_id}/close", response_model=ChatSessionWorkflowResponse)
    async def close_chat_session(
        session_id: str,
        request: ChatSessionCloseRequest | None = None,
    ) -> ChatSessionWorkflowResponse:
        request = request or ChatSessionCloseRequest()
        target = session_target(ChatRequest(config_path=request.config_path, vault_path=request.vault_path, vault_id=request.vault_id, messages=[{"role": "user", "content": "close session"}]))
        closed = services.chat_sessions.close_session(target.path, session_id)
        should_auto_ingest, reason, policy_request = _auto_ingest_decision(request, closed)
        if not should_auto_ingest:
            return ChatSessionWorkflowResponse(session=closed, reason=reason)
        started = _start_chat_session_ingest(services, session_id, policy_request)
        updated = services.chat_sessions.mark_ingest_started(target.path, session_id, started.run_id)
        return ChatSessionWorkflowResponse(session=updated, ingest_started=True, run_id=started.run_id, status=started.status, reason=reason)

    @router.post("/chat/sessions/{session_id}/retry", response_model=ChatResponse)
    async def retry_chat_session_turn(
        session_id: str,
        request: ChatSessionRetryRequest | None = None,
    ) -> ChatResponse:
        request = request or ChatSessionRetryRequest()
        target = session_target(ChatRequest(config_path=request.config_path, vault_path=request.vault_path, vault_id=request.vault_id, messages=[{"role": "user", "content": "retry session"}]))
        previous, user_message = services.chat_sessions.prepare_retry_latest_turn(target.path, session_id)
        retry_request = ChatRequest(
            session_id=session_id,
            config_path=request.config_path,
            vault_path=str(target.path),
            vault_id=target.vault_id,
            vault_ids=request.vault_ids,
            all_vaults=request.all_vaults,
            messages=[user_message],
            max_turns=request.max_turns,
            include_trace=request.include_trace,
            append_ledger=request.append_ledger,
            provider=request.provider,
            max_tokens=request.max_tokens,
        )
        try:
            return services.chat.chat(retry_request, services)
        except Exception:
            services.chat_sessions.restore_record(target.path, previous)
            raise

    return router


def _start_chat_session_ingest(services: ApplicationServices, session_id: str, request: ChatSessionIngestRequest):
    target = session_target(ChatRequest(config_path=request.config_path, vault_path=request.vault_path, vault_id=request.vault_id, messages=[{"role": "user", "content": "ingest session"}]))
    source_document = services.chat_sessions.to_source_document(target.path, session_id)
    ingest_request = IngestDocumentRunRequest(
        source_document=source_document,
        config_path=request.config_path,
        vault_path=str(target.path),
        vault_id=target.vault_id,
        provider=request.provider,
        max_tokens=request.max_tokens,
        write=request.write,
        write_report=request.write_report,
        append_ledger=request.append_ledger,
        auto_scoped_lint=request.auto_scoped_lint,
        auto_apply_safe_lint_fixes=request.auto_apply_safe_lint_fixes,
        scoped_lint_include_related=request.scoped_lint_include_related,
    )
    started = services.runs.start_ingest_document(ingest_request, services.ingest.run_document)
    services.chat_sessions.mark_ingest_started(target.path, session_id, started.run_id)
    return started


def _auto_ingest_decision(request: ChatSessionCloseRequest, session: ChatSessionRecord) -> tuple[bool, str, ChatSessionIngestRequest]:
    config = select_config_vault(load_config(request.config_path or default_config_path()), vault_path=request.vault_path, vault_id=request.vault_id)
    policy = config.chat.auto_ingest
    enabled = request.auto_ingest if request.auto_ingest is not None else policy.enabled
    ingest_request = request
    if request.auto_ingest is None:
        ingest_request = request.model_copy(
            update={
                "write": policy.write,
                "write_report": policy.write_report,
                "append_ledger": policy.append_ledger,
            }
        )
    if not enabled:
        return False, "Chat auto-ingest is disabled.", ingest_request
    user_turns = sum(1 for message in session.messages if message.role == "user")
    if user_turns < policy.min_user_turns:
        return False, f"Chat session has {user_turns} user turn(s), below min_user_turns={policy.min_user_turns}.", ingest_request
    return True, "Chat auto-ingest policy matched on session close.", ingest_request
