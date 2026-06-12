from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from knoarbor.audit.token_ledger import current_timestamp
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.chat import ChatMessageItem, ChatResponse, ChatSessionListResponse, ChatSessionRecord


class ChatSessionStore:
    """Vault-scoped storage for KnoArbor chat sessions."""

    def new_session_id(self) -> str:
        return _new_session_id()

    def list_sessions(self, vault_path: str | Path, *, limit: int = 50) -> ChatSessionListResponse:
        records = []
        for path in _sessions_dir(vault_path).glob("chat_*.json"):
            record = self._read_record_path(path)
            if record is not None:
                records.append(record)
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return ChatSessionListResponse(sessions=[record.summary() for record in records[: max(1, min(limit, 200))]])

    def read_session(self, vault_path: str | Path, session_id: str) -> ChatSessionRecord:
        path = _session_path(vault_path, session_id)
        if not path.exists():
            raise UserInputError(f"Chat session does not exist: {session_id}")
        record = self._read_record_path(path)
        if record is None:
            raise UserInputError(f"Chat session is unreadable: {session_id}")
        return record

    def load_existing(self, vault_path: str | Path, session_id: str | None) -> ChatSessionRecord | None:
        if not session_id:
            return None
        path = _session_path(vault_path, session_id)
        if not path.exists():
            return None
        return self._read_record_path(path)

    def persist_response(
        self,
        vault_path: str | Path,
        *,
        response: ChatResponse,
        request_messages: list[ChatMessageItem],
        vault_id: str | None,
        vault_name: str | None,
    ) -> ChatSessionRecord:
        now = current_timestamp()
        existing = self.load_existing(vault_path, response.session_id)
        session_id = response.session_id or _new_session_id()
        messages = _merge_messages(existing.messages if existing else [], response.messages or request_messages)
        title = existing.title if existing else _title_from_messages(messages)
        record = ChatSessionRecord(
            session_id=session_id,
            title=title,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            vault_id=vault_id,
            vault_name=vault_name,
            vault_path=str(Path(vault_path).expanduser().resolve()),
            messages=messages,
            citations=response.citations,
            tool_trace=response.tool_trace,
            events=response.events,
            run_links=response.run_links,
            memory_used=response.memory_used,
            memory_candidates=response.memory_candidates,
            memory_writes=response.memory_writes,
            stats=response.stats,
            warnings=response.warnings,
        )
        path = _session_path(vault_path, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def _read_record_path(self, path: Path) -> ChatSessionRecord | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ChatSessionRecord.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError):
            return None


def _sessions_dir(vault_path: str | Path) -> Path:
    return Path(vault_path).expanduser().resolve() / ".knoarbor" / "chat" / "sessions"


def _session_path(vault_path: str | Path, session_id: str) -> Path:
    clean = _clean_session_id(session_id)
    return _sessions_dir(vault_path) / f"{clean}.json"


def _clean_session_id(session_id: str) -> str:
    clean = session_id.strip()
    if not re.fullmatch(r"chat_[A-Za-z0-9_-]{4,64}", clean):
        raise UserInputError(f"Invalid chat session id: {session_id}")
    return clean


def _new_session_id() -> str:
    return f"chat_{uuid4().hex[:12]}"


def _merge_messages(existing: list[ChatMessageItem], latest: list[ChatMessageItem]) -> list[ChatMessageItem]:
    if not existing:
        return latest
    if len(latest) >= len(existing) and all(_message_key(latest[index]) == _message_key(existing[index]) for index in range(len(existing))):
        return latest
    merged = list(existing)
    for message in latest:
        if not merged or _message_key(merged[-1]) != _message_key(message):
            merged.append(message)
    return merged


def _message_key(message: ChatMessageItem) -> tuple[str, str, str | None]:
    return (message.role, message.content, message.tool_name)


def _title_from_messages(messages: list[ChatMessageItem]) -> str:
    for message in messages:
        if message.role == "user":
            title = re.sub(r"\s+", " ", message.content).strip()
            return title[:48] or "New chat"
    return "New chat"
