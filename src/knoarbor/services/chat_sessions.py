from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from knoarbor.audit.token_ledger import current_timestamp
from knoarbor.core.errors import StorageConflict, UserInputError
from knoarbor.core.schemas.chat import (
    ChatIngestCandidate,
    ChatMessageItem,
    ChatResponse,
    ChatSessionListResponse,
    ChatSessionRecord,
    ChatSessionSummary,
    ChatTurnRecord,
)
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.runtime import FileLock
from knoarbor.services.chat_messages import merge_messages, message_key
from knoarbor.services.chat_generated_images import delete_chat_request_artifacts, delete_chat_session_artifacts
from knoarbor.services.chat_trace_persistence import compact_tool_trace_for_persistence


class ChatSessionStore:
    """Vault-scoped storage for product chat sessions."""

    def new_session_id(self) -> str:
        return _new_session_id()

    def list_sessions(
        self,
        vault_path: str | Path,
        *,
        limit: int = 50,
        offset: int = 0,
        sessions_dir: str | Path | None = None,
    ) -> ChatSessionListResponse:
        summaries: list[ChatSessionSummary] = []
        for path in _sessions_dir(vault_path, sessions_dir=sessions_dir).glob("chat_*.json"):
            summary = self._read_summary_path(path)
            if summary is not None:
                summaries.append(summary)
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        page_limit = max(1, min(limit, 200))
        page_offset = max(0, offset)
        total_count = len(summaries)
        return ChatSessionListResponse(
            sessions=summaries[page_offset : page_offset + page_limit],
            total_count=total_count,
            offset=page_offset,
            limit=page_limit,
            has_more=page_offset + page_limit < total_count,
        )

    def read_session(self, vault_path: str | Path, session_id: str, *, sessions_dir: str | Path | None = None) -> ChatSessionRecord:
        path = _session_path(vault_path, session_id, sessions_dir=sessions_dir)
        if not path.exists():
            raise UserInputError(f"Chat session does not exist: {session_id}")
        record = self._read_record_path(path)
        if record is None:
            raise UserInputError(f"Chat session is unreadable: {session_id}")
        return record

    def delete_session(
        self,
        vault_path: str | Path,
        session_id: str,
        expected_session_revision: int,
        *,
        sessions_dir: str | Path | None = None,
    ) -> bool:
        path = _session_path(vault_path, session_id, sessions_dir=sessions_dir)
        with FileLock(path.with_suffix(".lock")):
            record = self.read_session(vault_path, session_id, sessions_dir=sessions_dir)
            _require_session_revision(record, expected_session_revision)
            path.unlink()
            delete_chat_session_artifacts(vault_path, session_id)
            return True

    def remove_turn(
        self,
        vault_path: str | Path,
        session_id: str,
        turn_id: str,
        expected_session_revision: int,
        *,
        sessions_dir: str | Path | None = None,
    ) -> ChatSessionRecord:
        path = _session_path(vault_path, session_id, sessions_dir=sessions_dir)
        with FileLock(path.with_suffix(".lock")):
            record = self.read_session(vault_path, session_id, sessions_dir=sessions_dir)
            _require_session_revision(record, expected_session_revision)
            if record.status != "active":
                raise UserInputError("Only active chat sessions can have turns removed.")
            turn = next((item for item in record.turns if item.turn_id == turn_id), None)
            if turn is None:
                raise UserInputError(f"Chat turn does not exist: {turn_id}")
            messages = _trim_turn_messages(record.messages, turn)
            turns = [item.model_copy(update={"index": index}) for index, item in enumerate(item for item in record.turns if item.turn_id != turn_id)]
            updated = record.model_copy(update={
                "session_revision": record.session_revision + 1,
                "messages": messages,
                "turns": turns,
                "updated_at": current_timestamp(),
                "ingest_candidate": None,
            })
            self._write_record(vault_path, updated, sessions_dir=sessions_dir)
            delete_chat_request_artifacts(
                vault_path,
                session_id,
                turn.request_id,
                stored_paths=_turn_stored_image_paths(turn),
            )
            return updated

    def update_title(
        self,
        vault_path: str | Path,
        session_id: str,
        title: str,
        expected_session_revision: int,
        *,
        sessions_dir: str | Path | None = None,
    ) -> ChatSessionRecord:
        path = _session_path(vault_path, session_id, sessions_dir=sessions_dir)
        with FileLock(path.with_suffix(".lock")):
            record = self.read_session(vault_path, session_id, sessions_dir=sessions_dir)
            _require_session_revision(record, expected_session_revision)
            clean_title = _compact_title(title)
            if not clean_title:
                raise UserInputError("Chat session title cannot be empty.")
            updated = record.model_copy(
                update={
                    "session_revision": record.session_revision + 1,
                    "title": clean_title[:160],
                    "updated_at": current_timestamp(),
                }
            )
            self._write_record(vault_path, updated, sessions_dir=sessions_dir)
            return updated

    def load_existing(self, vault_path: str | Path, session_id: str | None, *, sessions_dir: str | Path | None = None) -> ChatSessionRecord | None:
        if not session_id:
            return None
        path = _session_path(vault_path, session_id, sessions_dir=sessions_dir)
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
        sessions_dir: str | Path | None = None,
        replacement_turn_id: str | None = None,
    ) -> ChatSessionRecord:
        path = _session_path(vault_path, response.session_id, sessions_dir=sessions_dir)
        with FileLock(path.with_suffix(".lock")):
            existing = self._read_record_path(path) if path.exists() else None
            record = _response_record(
                vault_path=vault_path,
                response=response,
                request_messages=request_messages,
                vault_id=vault_id,
                vault_name=vault_name,
                existing=existing,
                replacement_turn_id=replacement_turn_id,
            )
            self._write_record(vault_path, record, sessions_dir=sessions_dir)
            if existing is not None and replacement_turn_id is not None:
                replaced = existing.turns[-1]
                delete_chat_request_artifacts(
                    vault_path,
                    response.session_id,
                    replaced.request_id,
                    stored_paths=_turn_stored_image_paths(replaced),
                )
            return record

    def close_session(
        self,
        vault_path: str | Path,
        session_id: str,
        expected_session_revision: int,
        *,
        sessions_dir: str | Path | None = None,
    ) -> ChatSessionRecord:
        path = _session_path(vault_path, session_id, sessions_dir=sessions_dir)
        with FileLock(path.with_suffix(".lock")):
            record = self.read_session(vault_path, session_id, sessions_dir=sessions_dir)
            _require_session_revision(record, expected_session_revision)
            closed = record.model_copy(
                update={
                    "session_revision": record.session_revision + 1,
                    "status": "closed",
                    "closed_at": current_timestamp(),
                    "updated_at": current_timestamp(),
                    "ingest_candidate": build_ingest_candidate(record),
                }
            )
            self._write_record(vault_path, closed, sessions_dir=sessions_dir)
            return closed

    def mark_ingest_started(self, vault_path: str | Path, session_id: str, run_id: str, *, sessions_dir: str | Path | None = None) -> ChatSessionRecord:
        record = self.read_session(vault_path, session_id, sessions_dir=sessions_dir)
        updated = record.model_copy(update={"last_ingest_run_id": run_id, "last_ingested_at": current_timestamp(), "updated_at": current_timestamp()})
        self._write_record(vault_path, updated, sessions_dir=sessions_dir)
        return updated

    def prepare_retry_turn(
        self,
        vault_path: str | Path,
        session_id: str,
        target_turn_id: str,
        expected_session_revision: int,
        *,
        sessions_dir: str | Path | None = None,
    ) -> tuple[ChatSessionRecord, ChatMessageItem]:
        record = self.read_session(vault_path, session_id, sessions_dir=sessions_dir)
        _require_session_revision(record, expected_session_revision)
        if record.status != "active":
            raise UserInputError("Only active chat sessions can regenerate an answer.")
        if not record.turns:
            raise UserInputError("Chat session has no completed turn to regenerate.")
        retry_turn = record.turns[-1]
        if retry_turn.turn_id != target_turn_id:
            raise StorageConflict("Only the current latest Chat turn can be regenerated.")
        return record, retry_turn.user_message

    def restore_record(self, vault_path: str | Path, record: ChatSessionRecord, *, sessions_dir: str | Path | None = None) -> None:
        self._write_record(vault_path, record, sessions_dir=sessions_dir)

    def to_source_document(
        self,
        vault_path: str | Path,
        session_id: str,
        *,
        turn_ids: list[str] | None = None,
        expected_session_revision: int | None = None,
        sessions_dir: str | Path | None = None,
        source_title: str | None = None,
    ) -> SourceDocument:
        record = self.read_session(vault_path, session_id, sessions_dir=sessions_dir)
        if expected_session_revision is not None:
            _require_session_revision(record, expected_session_revision)
        path = _session_path(vault_path, session_id, sessions_dir=sessions_dir)
        raw_text = path.read_text(encoding="utf-8")
        requested_turns = [turn for turn in record.turns if turn.turn_id in turn_ids] if turn_ids is not None else list(record.turns)
        if turn_ids is not None and {turn.turn_id for turn in requested_turns} != set(turn_ids):
            raise UserInputError("One or more selected Chat turn identities no longer exist.")
        ineligible = [turn.index for turn in requested_turns if not _turn_is_ingest_eligible(turn)]
        if ineligible and turn_ids is not None:
            raise UserInputError(f"Chat turn(s) are not grounded and cannot be ingested: {', '.join(map(str, ineligible))}")
        selected_turns = [turn for turn in requested_turns if _turn_is_ingest_eligible(turn)]
        if not selected_turns:
            raise UserInputError("Chat session has no grounded turn eligible for ingest.")
        selected_messages = [message for turn in selected_turns for message in (turn.user_message, turn.assistant_message)]
        title = _source_title(source_title, record.title)
        payload = _source_payload(record, selected_messages=selected_messages, selected_turns=selected_turns, title=title)
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
                    for index, message in enumerate(selected_messages)
                ],
            ),
            metadata={
                "title": title,
                "session_id": record.session_id,
                "source_app": "knoarbor",
                "message_count": len(selected_messages),
                "total_message_count": len(record.messages),
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
            record = ChatSessionRecord.model_validate(
                _migrate_session_payload(payload)
            )
            return _compact_migrated_trace(record)
        except (OSError, json.JSONDecodeError, ValidationError):
            return None

    def _read_summary_path(self, path: Path) -> ChatSessionSummary | None:
        try:
            prefix = _session_summary_prefix(path)
            payload = json.loads(prefix)
            record = ChatSessionRecord.model_validate(
                _migrate_session_payload(payload)
            )
            return record.summary()
        except (OSError, json.JSONDecodeError, ValidationError, ValueError):
            record = self._read_record_path(path)
            return record.summary() if record is not None else None

    def _write_record(self, vault_path: str | Path, record: ChatSessionRecord, *, sessions_dir: str | Path | None = None) -> None:
        path = _session_path(vault_path, record.session_id, sessions_dir=sessions_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(record.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


def _migrate_session_payload(payload: object) -> object:
    """Upgrade the one supported v3 session shape to the linear v4 record."""

    if not isinstance(payload, dict) or payload.get("schema_version") != "chat_session.v3":
        return payload
    migrated = dict(payload)
    migrated["schema_version"] = "chat_session.v4"
    migrated.pop("topic_anchor", None)
    migrated.pop("retrieval_continuation", None)
    stats = migrated.get("stats")
    if isinstance(stats, dict):
        migrated["stats"] = {
            key: value
            for key, value in stats.items()
            if key not in {"topic_anchor", "turn_intent"}
        }
    turns = migrated.get("turns")
    if isinstance(turns, list):
        migrated["turns"] = [
            {
                key: value
                for key, value in turn.items()
                if key not in {"topic_anchor", "retrieval_continuation"}
            }
            if isinstance(turn, dict)
            else turn
            for turn in turns
        ]
        for turn in migrated["turns"]:
            if isinstance(turn, dict) and isinstance(turn.get("stats"), dict):
                turn["stats"] = {
                    key: value
                    for key, value in turn["stats"].items()
                    if key not in {"topic_anchor", "turn_intent"}
                }
    return migrated


def _session_summary_prefix(path: Path) -> str:
    """Read only the top-level fields preceding the heavyweight turn records."""

    marker = '\n  "turns":'
    text = ""
    with path.open("r", encoding="utf-8") as stream:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                raise ValueError("session record has no canonical turns field")
            text += chunk
            marker_index = text.find(marker)
            if marker_index < 0:
                continue
            prefix = text[:marker_index].rstrip()
            if prefix.endswith(","):
                prefix = prefix[:-1]
            return f"{prefix}\n}}"


def _compact_migrated_trace(
    record: ChatSessionRecord,
) -> ChatSessionRecord:
    """Drop duplicated legacy trace state from the in-memory v4 view."""

    return record.model_copy(
        update={
            "turns": [
                turn.model_copy(
                    update={
                        "tool_trace": compact_tool_trace_for_persistence(
                            turn.tool_trace
                        )
                    }
                )
                for turn in record.turns
            ],
            # v4 turns are authoritative. v3 duplicated the latest trace at
            # session level; retain it only for malformed historical records
            # that have no turn projection to serve.
            "tool_trace": (
                []
                if record.turns
                else compact_tool_trace_for_persistence(record.tool_trace)
            ),
        }
    )


def _sessions_dir(vault_path: str | Path, *, sessions_dir: str | Path | None = None) -> Path:
    if sessions_dir is not None:
        return Path(sessions_dir).expanduser().resolve()
    return Path(vault_path).expanduser().resolve() / ".knoarbor" / "chat" / "sessions"


def _require_session_revision(record: ChatSessionRecord, expected: int) -> None:
    if record.session_revision != expected:
        raise StorageConflict(
            f"Chat session revision changed: expected {expected}, current {record.session_revision}."
        )


def _session_path(vault_path: str | Path, session_id: str, *, sessions_dir: str | Path | None = None) -> Path:
    clean = _clean_session_id(session_id)
    return _sessions_dir(vault_path, sessions_dir=sessions_dir) / f"{clean}.json"


def _clean_session_id(session_id: str) -> str:
    clean = session_id.strip()
    if not re.fullmatch(r"chat_[A-Za-z0-9_-]{4,64}", clean):
        raise UserInputError(f"Invalid chat session id: {session_id}")
    return clean


def _new_session_id() -> str:
    return f"chat_{uuid4().hex[:12]}"


def _trim_latest_turn_messages(messages: list[ChatMessageItem], turn: ChatTurnRecord) -> list[ChatMessageItem]:
    if len(messages) >= 2 and message_key(messages[-2]) == message_key(turn.user_message) and message_key(messages[-1]) == message_key(turn.assistant_message):
        return messages[:-2]
    for index in range(len(messages) - 2, -1, -1):
        if message_key(messages[index]) == message_key(turn.user_message):
            return messages[:index]
    raise UserInputError("Could not locate the latest chat turn in session messages.")


def _trim_turn_messages(messages: list[ChatMessageItem], turn: ChatTurnRecord) -> list[ChatMessageItem]:
    user_key = message_key(turn.user_message)
    assistant_key = message_key(turn.assistant_message)
    result: list[ChatMessageItem] = []
    skip_next = False
    for message in messages:
        key = message_key(message)
        if key == user_key and not skip_next:
            skip_next = True
            continue
        if skip_next and key == assistant_key:
            skip_next = False
            continue
        result.append(message)
    return result


def _title_from_messages(messages: list[ChatMessageItem]) -> str:
    for message in messages:
        if message.role == "user":
            title = re.sub(r"\s+", " ", message.content).strip()
            return title[:48] or "New chat"
    return "New chat"


def _compact_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:80] or "message"


def _source_payload(
    record: ChatSessionRecord,
    *,
    selected_messages: list[ChatMessageItem] | None = None,
    selected_turns: list[ChatTurnRecord] | None = None,
    title: str | None = None,
) -> dict[str, object]:
    messages = selected_messages if selected_messages is not None else record.messages
    turns = selected_turns if selected_turns is not None else record.turns
    return {
        "schema_version": "knoarbor_chat_extract.v2",
        "source_app": "knoarbor",
        "session_id": record.session_id,
        "title": title or record.title,
        "session_start": record.created_at,
        "last_updated": record.updated_at,
        "closed_at": record.closed_at,
        "message_count": len(messages),
        "messages": [
            {
                "index": index,
                "raw_index": index,
                "role": message.role,
                "content": message.content,
                "tool_name": message.tool_name,
            }
            for index, message in enumerate(messages)
        ],
        "turns": [
            {
                "index": turn.index,
                "created_at": turn.created_at,
                "user": turn.user_message.content,
                "assistant": turn.assistant_message.content,
                "answer_provenance": turn.answer_provenance.model_dump(mode="json"),
                "citations": [citation.model_dump(mode="json") for citation in turn.citations],
                "warnings": turn.warnings,
            }
            for turn in turns
        ],
        "citations": [citation.model_dump(mode="json") for citation in record.citations],
        "run_links": [link.model_dump(mode="json") for link in record.run_links],
        "warnings": record.warnings,
    }


def _source_title(candidate: str | None, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", (candidate or fallback or "").strip())
    return cleaned[:160] or "KnoArbor Chat"


def build_ingest_candidate(record: ChatSessionRecord) -> ChatIngestCandidate:
    grounded_turns = [turn for turn in record.turns if _turn_is_ingest_eligible(turn)]
    user_turns = len(grounded_turns)
    assistant_turns = len(grounded_turns)
    citations = [citation for turn in grounded_turns for citation in turn.citations]
    citation_count = len({(citation.vault_id or "", citation.evidence_id or citation.path or citation.run_id or citation.title or "") for citation in citations})
    turn_count = len(grounded_turns)
    signals: list[str] = []

    if user_turns >= 2:
        signals.append("multi_turn")
    if citation_count >= 2:
        signals.append("uses_wiki_sources")
    if any(turn.memory_candidates for turn in record.turns) or record.memory_candidates:
        signals.append("memory_candidates")
    if any(_contains_durable_knowledge(message.content) for turn in grounded_turns for message in (turn.user_message, turn.assistant_message)):
        signals.append("durable_knowledge_language")
    if turn_count >= 2 and any(turn.citations for turn in record.turns):
        signals.append("grounded_followup")

    should_ingest = len(signals) >= 2 or (user_turns >= 3 and citation_count >= 1)
    reason = "Chat session contains durable knowledge signals." if should_ingest else "Chat session does not have enough durable knowledge signals yet."
    return ChatIngestCandidate(
        should_ingest=should_ingest,
        reason=reason,
        user_turns=user_turns,
        assistant_turns=assistant_turns,
        citation_count=citation_count,
        signal_count=len(signals),
        signals=signals,
    )


def _turn_is_ingest_eligible(turn: ChatTurnRecord) -> bool:
    return turn.answer_provenance.mode in {"knowledge_grounded", "knowledge_grounded_with_gap"}


def _contains_durable_knowledge(text: str) -> bool:
    lowered = text.lower()
    signals = (
        "decision",
        "architecture",
        "design",
        "workflow",
        "implementation",
        "tradeoff",
        "root cause",
        "结论",
        "决策",
        "架构",
        "设计",
        "流程",
        "实现",
        "根因",
        "方案",
    )
    return any(signal in lowered for signal in signals)


def _turn_from_response(
    response: ChatResponse,
    request_messages: list[ChatMessageItem],
    assistant_message: ChatMessageItem,
    index: int,
    created_at: str,
) -> ChatTurnRecord | None:
    user_message = _last_message_with_role(request_messages, "user")
    if user_message is None or assistant_message is None:
        return None
    return ChatTurnRecord(
        index=index,
        turn_id=response.turn_id,
        request_id=response.request_id,
        execution_id=response.execution_id,
        created_at=created_at,
        user_message=user_message,
        assistant_message=assistant_message,
        answer_provenance=response.answer_provenance,
        citations=response.citations,
        hidden_evidence_count=response.hidden_evidence_count,
        citation_warnings=response.citation_warnings,
        tool_trace=compact_tool_trace_for_persistence(response.tool_trace),
        events=response.events,
        run_links=response.run_links,
        memory_used=response.memory_used,
        memory_candidates=response.memory_candidates,
        memory_writes=response.memory_writes,
        stats=response.stats,
        warnings=response.warnings,
    )


def _response_record(
    *,
    vault_path: str | Path,
    response: ChatResponse,
    request_messages: list[ChatMessageItem],
    vault_id: str | None,
    vault_name: str | None,
    existing: ChatSessionRecord | None,
    replacement_turn_id: str | None,
) -> ChatSessionRecord:
    now = current_timestamp()
    session_id = response.session_id or _new_session_id()
    expected_revision = (existing.session_revision if existing else 0) + 1
    if response.session_revision != expected_revision:
        raise StorageConflict(
            f"Chat session revision changed before commit: expected {response.session_revision - 1}, "
            f"current {existing.session_revision if existing else 0}."
        )
    if replacement_turn_id is not None:
        if existing is None or existing.status != "active" or not existing.turns:
            raise StorageConflict("Chat retry target is no longer an active completed turn.")
        if existing.turns[-1].turn_id != replacement_turn_id:
            raise StorageConflict("Chat retry target changed before replacement commit.")

    assistant_message = ChatMessageItem(role="assistant", content=response.answer)
    turn_index = len(existing.turns) - 1 if existing is not None and replacement_turn_id is not None else len(existing.turns if existing else [])
    turn = _turn_from_response(response, request_messages, assistant_message, turn_index, now)
    if turn is None:
        raise UserInputError("Chat response has no user turn to persist.")

    if existing is not None and replacement_turn_id is not None:
        messages = [
            *_trim_latest_turn_messages(existing.messages, existing.turns[-1]),
            turn.user_message,
            assistant_message,
        ]
        turns = [*existing.turns[:-1], turn]
    else:
        messages = merge_messages(existing.messages if existing else [], [*request_messages, assistant_message])
        turns = list(existing.turns if existing else [])
        if not _turn_already_recorded(turns, turn):
            turns.append(turn)

    return ChatSessionRecord(
        session_id=session_id,
        session_revision=response.session_revision,
        title=existing.title if existing else _title_from_messages(messages),
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
        turns=turns,
        citations=response.citations,
        # Per-turn traces are authoritative. Do not duplicate the latest turn's
        # trace at session level, especially when a response carried Raw text.
        tool_trace=[],
        events=response.events,
        run_links=response.run_links,
        memory_used=response.memory_used,
        memory_candidates=response.memory_candidates,
        memory_writes=response.memory_writes,
        stats=response.stats,
        warnings=response.warnings,
    )


def _last_message_with_role(messages: list[ChatMessageItem], role: str) -> ChatMessageItem | None:
    for message in reversed(messages):
        if message.role == role:
            return message
    return None


def _turn_already_recorded(turns: list[ChatTurnRecord], turn: ChatTurnRecord) -> bool:
    return any(existing.request_id == turn.request_id for existing in turns)


def _turn_stored_image_paths(turn: ChatTurnRecord) -> set[str]:
    paths: set[str] = set()
    for trace in turn.tool_trace:
        if trace.tool != "generate_image":
            continue
        images = trace.result.get("images")
        if not isinstance(images, list):
            continue
        for image in images:
            if isinstance(image, dict) and image.get("stored_path"):
                paths.add(str(image["stored_path"]))
    return paths
