from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from knoarbor.audit.token_ledger import append_chat_token_records, current_timestamp
from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest, ChatResponse
from knoarbor.core.vault_selection import ResolvedVault
from knoarbor.services.chat_context import session_target

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


@dataclass(frozen=True)
class ChatPersistenceCoordinator:
    """Persist chat session records and token ledger entries after orchestration."""

    def persist_response(
        self,
        services: ApplicationServices,
        *,
        chat_target: ResolvedVault,
        request: ChatRequest,
        response: ChatResponse,
        request_messages: list[ChatMessageItem],
        call_records: list[dict[str, object]],
    ) -> ChatResponse:
        record = services.chat_sessions.persist_response(
            chat_target.path,
            response=response,
            request_messages=request_messages,
            vault_id=chat_target.vault_id,
            vault_name=chat_target.vault_name,
        )
        response.session_id = record.session_id
        if request.append_ledger:
            self.append_ledger(request, response, call_records)
        return response

    def append_ledger(self, request: ChatRequest, response: ChatResponse, calls: list[dict[str, object]]) -> None:
        vault = session_target(request)
        tool_plan = response.stats.get("tool_plan") if isinstance(response.stats.get("tool_plan"), dict) else {}
        first_call = (tool_plan.get("tool_calls") or [{}])[0] if isinstance(tool_plan.get("tool_calls"), list) else {}
        first_arguments = first_call.get("arguments") if isinstance(first_call, dict) else {}
        retrieval_mode = first_arguments.get("mode") if isinstance(first_arguments, dict) else None
        append_chat_token_records(
            vault.path,
            {
                "chat_id": response.stats.get("chat_id"),
                "created_at": current_timestamp(),
                "finished_at": current_timestamp(),
                "mode": retrieval_mode or "model_planned",
                "provider": response.stats.get("provider"),
                "model": response.stats.get("model"),
                "calls": calls,
                "citations": [citation.model_dump() for citation in response.citations],
                "tool_trace": [item.model_dump() for item in response.tool_trace],
            },
        )
