from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest, ChatSessionRecord
from knoarbor.core.schemas.memory import MemoryRecord
from knoarbor.core.vaults import VIRTUAL_ALL_VAULT_ID
from knoarbor.core.vault_selection import ResolvedVault, resolve_single_vault
from knoarbor.services.chat_dependencies import ChatMemoryDependencies
from knoarbor.services.chat_messages import merge_messages
from knoarbor.storage.vault_layout import app_state_ledger_relative_path, ledger_relative_path, runtime_root
from knoarbor.semantic.llm import ChatMessage


_RENDERED_IMAGE_LINE_RE = re.compile(
    r"(?m)^[ \t]*!\[[^\]\n]*\]\([^\n]*\)[ \t]*$"
)
_PUBLIC_CITATION_SUFFIX_RE = re.compile(
    r"[ \t]+(?P<markers>(?:\[\d{1,3}\][ \t]*)+)"
    r"(?=(?:[。.!！?？])?[ \t]*(?:\n|$))"
)
_GENERATED_IMAGE_LABEL_RE = re.compile(
    r"(?m)^[ \t]*\*\*(?:本轮生成图片（非知识库证据）|"
    r"Generated this turn \(not knowledge-base evidence\))\*\*[ \t]*$"
)

@dataclass(frozen=True)
class ChatContextBundle:
    model_messages: list[ChatMessage]
    conversation_messages: list[ChatMessageItem]
    memory_used: list[MemoryRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChatSessionTarget:
    path: Path
    sessions_dir: Path
    token_ledger_path: str
    token_ledger_lock_path: Path | None
    vault_id: str | None
    vault_name: str | None


class ChatContextEngine:
    """Build model context for bounded product chat sessions."""

    def build(
        self,
        request: ChatRequest,
        services: ChatMemoryDependencies,
        *,
        chat_id: str,
        system_prompt: str,
        existing_session: ChatSessionRecord | None = None,
    ) -> ChatContextBundle:
        conversation_messages = merge_messages(existing_session.messages if existing_session else [], [request.message])
        warnings: list[str] = []
        memory_used: list[MemoryRecord] = []
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="system", content=f"Workspace context:\n{json.dumps(_workspace_context(request), ensure_ascii=False)}"),
        ]
        memory_context, memory_used, memory_warnings = self._memory_context(request, services, chat_id)
        warnings.extend(memory_warnings)
        if memory_context:
            messages.append(ChatMessage(role="system", content=memory_context))
        return ChatContextBundle(
            model_messages=messages,
            conversation_messages=conversation_messages,
            memory_used=memory_used,
            warnings=warnings,
        )

    def _memory_context(self, request: ChatRequest, services: ChatMemoryDependencies, chat_id: str) -> tuple[str, list[MemoryRecord], list[str]]:
        target = memory_target(request)
        if target is None:
            return "", [], []
        config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
        result = services.memory.recall(
            vault_path=target.path,
            vault_id=target.vault_id,
            query=request.message.content,
            config=config.memory,
            chat_id=chat_id,
        )
        return result.context_block, result.records, result.warnings


def session_dialogue_context(
    existing_session: ChatSessionRecord | None,
) -> list[dict[str, str]]:
    """Project persisted history into model-visible dialogue only."""

    if existing_session is None:
        return []
    return [
        {
            "user": turn.user_message.content,
            "assistant": _model_visible_assistant_text(
                turn.assistant_message.content,
                citation_count=len(turn.citations),
            ),
        }
        for turn in existing_session.turns
    ]


def _model_visible_assistant_text(
    content: str,
    *,
    citation_count: int,
) -> str:
    """Remove code-rendered presentation while retaining substantive dialogue."""

    text = _RENDERED_IMAGE_LINE_RE.sub("", content)
    text = _GENERATED_IMAGE_LABEL_RE.sub("", text)
    if citation_count:
        def remove_rendered_citation_suffix(match: re.Match[str]) -> str:
            indexes = [
                int(value)
                for value in re.findall(r"\[(\d{1,3})\]", match.group("markers"))
            ]
            return (
                ""
                if indexes
                and all(1 <= index <= citation_count for index in indexes)
                else match.group(0)
            )

        text = _PUBLIC_CITATION_SUFFIX_RE.sub(
            remove_rendered_citation_suffix,
            text,
        )
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def memory_target(request: ChatRequest) -> ResolvedVault | None:
    if request.all_vaults or request.vault_id == VIRTUAL_ALL_VAULT_ID:
        return None
    return resolve_single_vault(request.vault_path, request.vault_id, request.config_path)


def session_target(
    *,
    config_path: str | None,
    vault_path: str | None,
    vault_id: str | None,
    all_vaults: bool = False,
) -> ChatSessionTarget:
    """Resolve chat-session storage without requiring a conversational request."""
    if all_vaults or vault_id == VIRTUAL_ALL_VAULT_ID:
        return _global_chat_target(config_path)
    vault = resolve_single_vault(vault_path, vault_id, config_path)
    return ChatSessionTarget(
        path=vault.path,
        sessions_dir=runtime_root(vault.path) / "chat" / "sessions",
        token_ledger_path=ledger_relative_path("token"),
        token_ledger_lock_path=None,
        vault_id=vault.vault_id,
        vault_name=vault.vault_name,
    )


def _global_chat_target(config_path: str | None) -> ChatSessionTarget:
    config_file = Path(config_path).expanduser().resolve() if config_path else default_config_path()
    state_root = config_file.parent / "state"
    return ChatSessionTarget(
        path=state_root,
        sessions_dir=state_root / "chat" / "sessions",
        token_ledger_path=app_state_ledger_relative_path("token"),
        token_ledger_lock_path=state_root / "locks" / "token.write.lock",
        vault_id=VIRTUAL_ALL_VAULT_ID,
        vault_name="All vaults",
    )


def latest_user_text(messages: list[ChatMessageItem]) -> str:
    for item in reversed(messages):
        if item.role == "user":
            return item.content
    return messages[-1].content if messages else ""


def _workspace_context(request: ChatRequest) -> dict[str, object]:
    return {
        "active_vault_id": request.vault_id,
        "vault_ids": request.vault_ids,
        "all_vaults": request.all_vaults,
    }
