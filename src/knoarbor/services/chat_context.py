from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest, ChatSessionRecord
from knoarbor.core.schemas.memory import MemoryRecord
from knoarbor.core.vaults import VIRTUAL_ALL_VAULT_ID
from knoarbor.entrypoints.vault_selection import ResolvedVault, resolve_single_vault
from knoarbor.semantic.llm import ChatMessage

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


SYSTEM_PROMPT = (Path(__file__).parents[1] / "semantic/prompts/wiki_chat_answer.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class ChatContextBundle:
    model_messages: list[ChatMessage]
    conversation_messages: list[ChatMessageItem]
    memory_used: list[MemoryRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ChatContextEngine:
    """Build model context for bounded KnoArbor chat sessions."""

    def build(
        self,
        request: ChatRequest,
        services: ApplicationServices,
        *,
        chat_id: str,
        existing_session: ChatSessionRecord | None = None,
        system_prompt: str | None = None,
    ) -> ChatContextBundle:
        conversation_messages = _merge_messages(existing_session.messages if existing_session else [], request.messages)
        warnings: list[str] = []
        memory_used: list[MemoryRecord] = []
        messages = [
            ChatMessage(role="system", content=system_prompt or SYSTEM_PROMPT),
            ChatMessage(role="system", content=f"Workspace context:\n{json.dumps(_workspace_context(request), ensure_ascii=False)}"),
        ]
        memory_context, memory_used, memory_warnings = self._memory_context(request, services, chat_id)
        warnings.extend(memory_warnings)
        if memory_context:
            messages.append(ChatMessage(role="system", content=memory_context))
        for item in conversation_messages[-12:]:
            messages.append(ChatMessage(role=item.role, content=item.content))
        return ChatContextBundle(
            model_messages=messages,
            conversation_messages=conversation_messages,
            memory_used=memory_used,
            warnings=warnings,
        )

    def _memory_context(self, request: ChatRequest, services: ApplicationServices, chat_id: str) -> tuple[str, list[MemoryRecord], list[str]]:
        target = memory_target(request)
        if target is None:
            return "", [], []
        config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
        result = services.memory.recall(
            vault_path=target.path,
            vault_id=target.vault_id,
            query=latest_user_text(request.messages),
            config=config.memory,
            chat_id=chat_id,
        )
        return result.context_block, result.records, result.warnings


def memory_target(request: ChatRequest) -> ResolvedVault | None:
    if request.all_vaults or request.vault_id == VIRTUAL_ALL_VAULT_ID:
        return None
    return resolve_single_vault(request.vault_path, request.vault_id, request.config_path)


def session_target(request: ChatRequest) -> ResolvedVault:
    if request.all_vaults or request.vault_id == VIRTUAL_ALL_VAULT_ID:
        return ResolvedVault(path=_global_chat_root(request.config_path), vault_id=VIRTUAL_ALL_VAULT_ID, vault_name="All vaults")
    return resolve_single_vault(request.vault_path, request.vault_id, request.config_path)


def _global_chat_root(config_path: str | None) -> Path:
    config_file = Path(config_path).expanduser().resolve() if config_path else default_config_path()
    return config_file.parent / ".knoarbor" / "global_chat"


def latest_user_text(messages: list[ChatMessageItem]) -> str:
    for item in reversed(messages):
        if item.role == "user":
            return item.content
    return messages[-1].content if messages else ""


def _workspace_context(request: ChatRequest) -> dict[str, object]:
    return {
        "active_vault": {
            "vault_id": request.vault_id,
            "vault_path": request.vault_path,
        },
        "vault_ids": request.vault_ids,
        "all_vaults": request.all_vaults,
    }


def _merge_messages(existing: list[ChatMessageItem], latest: list[ChatMessageItem]) -> list[ChatMessageItem]:
    if not existing:
        return list(latest)
    if len(latest) >= len(existing) and all(_message_key(latest[index]) == _message_key(existing[index]) for index in range(len(existing))):
        return list(latest)
    merged = list(existing)
    for message in latest:
        if not merged or _message_key(merged[-1]) != _message_key(message):
            merged.append(message)
    return merged


def _message_key(message: ChatMessageItem) -> tuple[str, str, str | None]:
    return (message.role, message.content, message.tool_name)
