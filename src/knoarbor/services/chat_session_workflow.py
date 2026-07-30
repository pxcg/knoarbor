from __future__ import annotations

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSessionCloseRequest,
    ChatSessionIngestRequest,
    ChatSessionRecord,
    ChatSessionRetryRequest,
    ChatSessionWorkflowResponse,
)
from knoarbor.core.schemas.ingest_run import UnifiedIngestRequest
from knoarbor.core.vault_selection import ResolvedVault, resolve_single_vault
from knoarbor.core.vaults import VIRTUAL_ALL_VAULT_ID, select_config_vault
from knoarbor.services.chat_context import ChatSessionTarget, session_target
from knoarbor.services.chat_dependencies import ChatWorkflowDependencies


def start_chat_session_ingest(services: ChatWorkflowDependencies, session_id: str, request: ChatSessionIngestRequest):
    source_target = session_target(
        config_path=request.config_path,
        vault_path=request.vault_path,
        vault_id=request.vault_id,
    )
    source_document = services.chat_sessions.to_source_document(
        source_target.path,
        session_id,
        turn_ids=request.turn_ids,
        expected_session_revision=request.expected_session_revision,
        sessions_dir=source_target.sessions_dir,
        source_title=request.source_title,
    )
    ingest_target = _chat_ingest_target(source_target, request)
    ingest_request = UnifiedIngestRequest(
        kind="document",
        execution="queued",
        source_document=source_document,
        config_path=request.config_path,
        vault_path=str(ingest_target.path),
        vault_id=ingest_target.vault_id,
        provider=request.provider,
        max_tokens=request.max_tokens,
        write=request.write,
        write_report=request.write_report,
        append_ledger=request.append_ledger,
        auto_scoped_lint=request.auto_scoped_lint,
        scoped_lint_include_related=request.scoped_lint_include_related,
    )
    started = services.ingest_coordinator.start(ingest_request)
    services.chat_sessions.mark_ingest_started(source_target.path, session_id, started.run_id, sessions_dir=source_target.sessions_dir)
    return started


def _chat_ingest_target(source_target: ChatSessionTarget, request: ChatSessionIngestRequest) -> ResolvedVault:
    if request.target_vault_path or request.target_vault_id:
        return resolve_single_vault(request.target_vault_path, request.target_vault_id, request.config_path)
    if source_target.vault_id == VIRTUAL_ALL_VAULT_ID:
        raise UserInputError("All-vault chat ingest requires target_vault_id or target_vault_path.")
    return ResolvedVault(path=source_target.path, vault_id=source_target.vault_id, vault_name=source_target.vault_name)


def close_chat_session_workflow(services: ChatWorkflowDependencies, session_id: str, request: ChatSessionCloseRequest) -> ChatSessionWorkflowResponse:
    target = session_target(
        config_path=request.config_path,
        vault_path=request.vault_path,
        vault_id=request.vault_id,
    )
    closed = services.chat_sessions.close_session(
        target.path,
        session_id,
        request.expected_session_revision,
        sessions_dir=target.sessions_dir,
    )
    should_auto_ingest, reason, policy_request = auto_ingest_decision(request, closed)
    if not should_auto_ingest:
        return ChatSessionWorkflowResponse(session=closed, reason=reason)
    started = start_chat_session_ingest(
        services,
        session_id,
        policy_request.model_copy(update={"expected_session_revision": closed.session_revision}),
    )
    updated = services.chat_sessions.read_session(target.path, session_id, sessions_dir=target.sessions_dir)
    return ChatSessionWorkflowResponse(session=updated, ingest_started=True, run_id=started.run_id, status=started.status, reason=reason)


def retry_chat_session_turn(services: ChatWorkflowDependencies, session_id: str, request: ChatSessionRetryRequest) -> ChatResponse:
    target = session_target(
        config_path=request.config_path,
        vault_path=request.vault_path,
        vault_id=request.vault_id,
        all_vaults=request.all_vaults,
    )
    previous, user_message = services.chat_sessions.prepare_retry_turn(
        target.path,
        session_id,
        request.target_turn_id,
        request.expected_session_revision,
        sessions_dir=target.sessions_dir,
    )
    retry_request = ChatRequest(
        request_id=request.request_id,
        execution_id=request.execution_id,
        session_id=session_id,
        expected_session_revision=previous.session_revision,
        config_path=request.config_path,
        vault_path=str(target.path),
        vault_id=target.vault_id,
        vault_ids=request.vault_ids,
        all_vaults=request.all_vaults,
        message=user_message,
        include_trace=request.include_trace,
        append_ledger=request.append_ledger,
        provider=request.provider,
        max_tokens=request.max_tokens,
    )
    return services.chat.chat(
        retry_request,
        services,
        replacement_turn_id=previous.turns[-1].turn_id,
    )


def auto_ingest_decision(request: ChatSessionCloseRequest, session: ChatSessionRecord) -> tuple[bool, str, ChatSessionIngestRequest]:
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
    user_turns = sum(
        1
        for turn in session.turns
        if turn.answer_provenance.mode in {"knowledge_grounded", "knowledge_grounded_with_gap"}
    )
    if user_turns < policy.min_user_turns:
        return False, f"Chat session has {user_turns} user turn(s), below min_user_turns={policy.min_user_turns}.", ingest_request
    return True, "Chat auto-ingest policy matched on session close.", ingest_request
