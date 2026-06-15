from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from knoarbor.audit.token_ledger import current_timestamp
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.chat import ChatMessageItem, ChatResponse, ChatSessionListResponse, ChatSessionRecord
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin


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

    def delete_session(self, vault_path: str | Path, session_id: str) -> bool:
        path = _session_path(vault_path, session_id)
        if not path.exists():
            raise UserInputError(f"Chat session does not exist: {session_id}")
        path.unlink()
        return True

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
            status="active",
            closed_at=None,
            last_ingest_run_id=existing.last_ingest_run_id if existing else None,
            last_ingested_at=existing.last_ingested_at if existing else None,
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

    def close_session(self, vault_path: str | Path, session_id: str) -> ChatSessionRecord:
        record = self.read_session(vault_path, session_id)
        closed = record.model_copy(update={"status": "closed", "closed_at": current_timestamp(), "updated_at": current_timestamp()})
        self._write_record(vault_path, closed)
        return closed

    def mark_ingest_started(self, vault_path: str | Path, session_id: str, run_id: str) -> ChatSessionRecord:
        record = self.read_session(vault_path, session_id)
        updated = record.model_copy(update={"last_ingest_run_id": run_id, "last_ingested_at": current_timestamp(), "updated_at": current_timestamp()})
        self._write_record(vault_path, updated)
        return updated

    def to_source_document(self, vault_path: str | Path, session_id: str) -> SourceDocument:
        record = self.read_session(vault_path, session_id)
        path = _session_path(vault_path, session_id)
        raw_text = path.read_text(encoding="utf-8")
        payload = _source_payload(record)
        return SourceDocument(
            source_id=f"knoarbor_chat:{record.session_id}",
            source_type="knoarbor_chat",
            origin=SourceOrigin(
                connector="knoarbor_chat",
                uri=f"knoarbor-chat://sessions/{record.session_id}",
                raw_path=str(path),
                original_path=path.as_uri(),
                created_at=record.created_at,
                updated_at=record.updated_at,
            ),
            content=SourceContent(
                format="json",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
                sections=[
                    {
                        "index": index,
                        "raw_index": index,
                        "role": message.role,
                        "title": _compact_title(message.content),
                        "content": message.content,
                        "tool_name": message.tool_name,
                    }
                    for index, message in enumerate(record.messages)
                ],
            ),
            metadata={
                "title": record.title,
                "session_id": record.session_id,
                "source_app": "knoarbor",
                "message_count": len(record.messages),
                "status": record.status,
                "closed_at": record.closed_at,
                "vault_id": record.vault_id,
                "vault_name": record.vault_name,
            },
            fingerprint=SourceFingerprint(
                content_hash=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
                connector_version="knoarbor-chat@1",
                parser_version="chat-session-source@1",
            ),
        )

    def _read_record_path(self, path: Path) -> ChatSessionRecord | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ChatSessionRecord.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError):
            return None

    def _write_record(self, vault_path: str | Path, record: ChatSessionRecord) -> None:
        path = _session_path(vault_path, record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


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


def _compact_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:80] or "message"


def _source_payload(record: ChatSessionRecord) -> dict[str, object]:
    return {
        "schema_version": "knoarbor_chat_extract.v1",
        "source_app": "knoarbor",
        "session_id": record.session_id,
        "title": record.title,
        "session_start": record.created_at,
        "last_updated": record.updated_at,
        "closed_at": record.closed_at,
        "message_count": len(record.messages),
        "messages": [
            {
                "index": index,
                "raw_index": index,
                "role": message.role,
                "content": message.content,
                "tool_name": message.tool_name,
            }
            for index, message in enumerate(record.messages)
        ],
        "citations": [citation.model_dump(mode="json") for citation in record.citations],
        "run_links": [link.model_dump(mode="json") for link in record.run_links],
        "warnings": record.warnings,
    }
