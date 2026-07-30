from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from knoarbor.audit.token_ledger import current_timestamp
from knoarbor.core.config import MemoryConfig
from knoarbor.core.schemas.chat import ChatMessageItem
from knoarbor.core.schemas.memory import MemoryCandidate, MemoryEvent, MemoryRecallResult, MemoryRecord
from knoarbor.storage.ledger import append_jsonl_ledger, read_jsonl_ledger

MEMORY_RECORDS_PATH = ".knoarbor/memory/records.jsonl"
MEMORY_CANDIDATES_PATH = ".knoarbor/memory/candidates.jsonl"
MEMORY_EVENTS_PATH = ".knoarbor/memory/events.jsonl"

EXPLICIT_MEMORY_PATTERNS = (
    re.compile(r"(?:请|帮我)?记住[:：]?\s*(?P<content>.+)", re.IGNORECASE),
    re.compile(r"(?:以后|后续|今后)(?:请|都|默认)?(?P<content>.+)", re.IGNORECASE),
    re.compile(r"(?:默认|偏好|我希望)(?P<content>.+)", re.IGNORECASE),
    re.compile(r"(?:remember|please remember|from now on|default to|prefer)\s*:?\s*(?P<content>.+)", re.IGNORECASE),
)


class MemoryService:
    """Vault-scoped memory recall and conservative explicit preference capture."""

    def recall(
        self,
        *,
        vault_path: Path,
        vault_id: str | None,
        query: str,
        config: MemoryConfig,
        chat_id: str,
    ) -> MemoryRecallResult:
        if not config.enabled:
            return MemoryRecallResult()
        records = self._active_records(vault_path)
        selected = _select_records(records, query)[: config.max_recalled_records]
        if not selected:
            return MemoryRecallResult()
        now = current_timestamp()
        for record in selected:
            self._append_event(
                vault_path,
                MemoryEvent(
                    event_type="recalled",
                    memory_id=record.id,
                    chat_id=chat_id,
                    vault_id=vault_id,
                    created_at=now,
                    message="Memory record recalled for chat context.",
                ),
            )
        return MemoryRecallResult(records=selected, context_block=_build_context_block(selected))

    def capture_explicit_memory(
        self,
        *,
        vault_path: Path,
        vault_id: str | None,
        messages: list[ChatMessageItem],
        config: MemoryConfig,
        chat_id: str,
        source_session: str | None = None,
    ) -> tuple[list[MemoryCandidate], list[MemoryRecord]]:
        if not config.enabled:
            return [], []
        latest_user = _latest_user_text(messages)
        content = _extract_explicit_memory(latest_user)
        if not content:
            return [], []
        now = current_timestamp()
        record = MemoryRecord(
            id=f"mem_{uuid4().hex[:12]}",
            scope="vault",
            vault_id=vault_id,
            category=_classify_memory(content),
            content=content,
            evidence=latest_user,
            confidence=0.9,
            risk="low",
            source_session=source_session,
            source_chat_id=chat_id,
            created_at=now,
            updated_at=now,
        )
        decision = "auto_write" if config.auto_write_explicit_low_risk else "candidate_review"
        status = "written" if decision == "auto_write" else "pending"
        candidate = MemoryCandidate(
            id=f"memcand_{uuid4().hex[:12]}",
            status=status,
            decision=decision,
            record=record,
            reason="Explicit low-risk user memory instruction.",
            created_at=now,
            resolved_at=now if status == "written" else None,
        )
        append_jsonl_ledger(vault_path, MEMORY_CANDIDATES_PATH, candidate.model_dump(mode="json"))
        self._append_event(
            vault_path,
            MemoryEvent(
                event_type="candidate_created",
                candidate_id=candidate.id,
                memory_id=record.id,
                chat_id=chat_id,
                vault_id=vault_id,
                created_at=now,
                message=candidate.reason,
            ),
        )
        if status != "written":
            return [candidate], []
        append_jsonl_ledger(vault_path, MEMORY_RECORDS_PATH, record.model_dump(mode="json"))
        self._append_event(
            vault_path,
            MemoryEvent(
                event_type="written",
                candidate_id=candidate.id,
                memory_id=record.id,
                chat_id=chat_id,
                vault_id=vault_id,
                created_at=now,
                message="Explicit low-risk memory written.",
            ),
        )
        return [candidate], [record]

    def _active_records(self, vault_path: Path) -> list[MemoryRecord]:
        output: list[MemoryRecord] = []
        for item in read_jsonl_ledger(vault_path, MEMORY_RECORDS_PATH):
            try:
                output.append(MemoryRecord.model_validate(item))
            except ValueError:
                continue
        return output

    def _append_event(self, vault_path: Path, event: MemoryEvent) -> None:
        append_jsonl_ledger(vault_path, MEMORY_EVENTS_PATH, event.model_dump(mode="json"))


def _latest_user_text(messages: list[ChatMessageItem]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content.strip()
    return ""


def _extract_explicit_memory(text: str) -> str:
    compact = " ".join(text.strip().split())
    if not compact:
        return ""
    for pattern in EXPLICIT_MEMORY_PATTERNS:
        match = pattern.search(compact)
        if not match:
            continue
        content = match.group("content").strip(" ：:。.")
        return content
    return ""


def _classify_memory(content: str) -> str:
    lowered = content.lower()
    if any(marker in lowered for marker in ("不要", "不能", "avoid", "never", "禁止")):
        return "constraint"
    if any(marker in lowered for marker in ("风格", "语气", "style", "tone")):
        return "style"
    if any(marker in lowered for marker in ("流程", "步骤", "workflow", "process")):
        return "workflow"
    return "preference"


def _select_records(records: list[MemoryRecord], query: str) -> list[MemoryRecord]:
    terms = set(re.findall(r"[\w\u4e00-\u9fff]+", query.lower()))
    selected: list[MemoryRecord] = []
    for record in records:
        content_terms = set(re.findall(r"[\w\u4e00-\u9fff]+", record.content.lower()))
        if record.category in {"preference", "style"} or terms.intersection(content_terms):
            selected.append(record)
    return selected


def _build_context_block(records: list[MemoryRecord]) -> str:
    lines = [
        "<knoarbor-memory-context>",
        "The following records are long-lived user or vault preferences. Treat them as background context, not as the latest user request.",
    ]
    for record in records:
        lines.append(f"- [{record.category}] {record.content}")
    lines.append("</knoarbor-memory-context>")
    return "\n".join(lines)
