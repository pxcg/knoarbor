from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from knoarbor.audit.token_ledger import append_chat_token_records, current_timestamp
from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest, ChatResponse
from knoarbor.services.chat_context import ChatSessionTarget, session_target
from knoarbor.services.chat_dependencies import ChatSessionDependencies


@dataclass(frozen=True)
class ChatPersistenceCoordinator:
    """Persist chat session records and token ledger entries after orchestration."""

    def persist_response(
        self,
        services: ChatSessionDependencies,
        *,
        chat_target: ChatSessionTarget,
        request: ChatRequest,
        response: ChatResponse,
        request_messages: list[ChatMessageItem],
        call_records: list[dict[str, object]],
        raise_if_cancelled: Callable[[], None] | None = None,
        replacement_turn_id: str | None = None,
    ) -> ChatResponse:
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        existing = services.chat_sessions.load_existing(
            chat_target.path,
            response.session_id,
            sessions_dir=chat_target.sessions_dir,
        )
        duplicate = next(
            (turn for turn in existing.turns if turn.request_id == response.request_id),
            None,
        ) if existing is not None else None
        if duplicate is not None:
            return response.model_copy(
                update={
                    "session_revision": existing.session_revision,
                    "turn_id": duplicate.turn_id,
                    "execution_id": duplicate.execution_id,
                    "answer": duplicate.assistant_message.content,
                    "answer_provenance": duplicate.answer_provenance,
                    "citations": duplicate.citations,
                    "hidden_evidence_count": duplicate.hidden_evidence_count,
                    "citation_warnings": duplicate.citation_warnings,
                    "tool_trace": duplicate.tool_trace,
                    "events": duplicate.events,
                    "run_links": duplicate.run_links,
                    "memory_used": duplicate.memory_used,
                    "memory_candidates": duplicate.memory_candidates,
                    "memory_writes": duplicate.memory_writes,
                    "stats": duplicate.stats,
                    "warnings": duplicate.warnings,
                }
            )
        record = services.chat_sessions.persist_response(
            chat_target.path,
            response=response,
            request_messages=request_messages,
            vault_id=chat_target.vault_id,
            vault_name=chat_target.vault_name,
            sessions_dir=chat_target.sessions_dir,
            replacement_turn_id=replacement_turn_id,
        )
        response.session_id = record.session_id
        response.session_revision = record.session_revision
        if request.append_ledger:
            if raise_if_cancelled is not None:
                raise_if_cancelled()
            self.append_ledger(request, response, call_records)
        return response

    def append_ledger(self, request: ChatRequest, response: ChatResponse, calls: list[dict[str, object]]) -> None:
        vault = session_target(
            config_path=request.config_path,
            vault_path=request.vault_path,
            vault_id=request.vault_id,
            all_vaults=request.all_vaults,
        )
        append_chat_token_records(
            vault.path,
            {
                "chat_id": response.stats.get("chat_id"),
                "request_id": response.request_id,
                "execution_id": response.execution_id,
                "turn_id": response.turn_id,
                "session_revision": response.session_revision,
                "created_at": current_timestamp(),
                "finished_at": current_timestamp(),
                "mode": response.answer_provenance.mode,
                "answer_mode": response.answer_provenance.mode,
                "query_outcome": response.answer_provenance.query_outcome,
                "chat_outcome": response.answer_provenance.chat_outcome,
                "grounding": "raw_evidence" if response.answer_provenance.mode.startswith("knowledge_grounded") else "none",
                "provider": response.stats.get("provider"),
                "model": response.stats.get("model"),
                "calls": calls,
                "citations": [citation.model_dump() for citation in response.citations],
            },
            ledger_path=vault.token_ledger_path,
            lock_path=vault.token_ledger_lock_path,
        )
