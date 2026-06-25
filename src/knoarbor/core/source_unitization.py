from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from io import StringIO
from typing import Any, Literal

from pydantic import BaseModel, Field

from knoarbor.core.checkpoints import session_unit_raw_index
from knoarbor.core.schemas.knowledge_extract import ContentUnit, ContentUnitRole, ContentUnitType, KnowledgeExtract
from knoarbor.core.schemas.sources import SourceDocument


SourceUnitizationRule = Literal[
    "markdown_heading",
    "parsed_document_structure",
    "chat_turn_group",
    "agent_task_turn_group",
    "conversation_topic",
    "selected_excerpt",
    "paragraph_group",
    "code_symbol",
    "html_section",
    "table_group",
    "ocr_region",
    "full_source",
]


class SourceUnitRange(BaseModel):
    from_index: int | None = None
    to_index: int | None = None


class SourceUnit(BaseModel):
    index: int = Field(..., ge=0)
    unit_type: ContentUnitType
    role: ContentUnitRole
    title: str | None = None
    content: str = ""
    source_range: SourceUnitRange = Field(default_factory=SourceUnitRange)
    structural_path: list[str] = Field(default_factory=list)
    raw_indexes: list[int] = Field(default_factory=list)
    rule: SourceUnitizationRule
    metadata: dict[str, object] = Field(default_factory=dict)


class SourceUnitizationResult(BaseModel):
    source_id: str
    source_type: str
    rule: SourceUnitizationRule
    fallback_rule: SourceUnitizationRule | None = None
    units: list[SourceUnit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def summary(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "rule": self.rule,
            "fallback_rule": self.fallback_rule,
            "unit_count": len(self.units),
            "unit_titles": [unit.title for unit in self.units],
            "warnings": list(self.warnings),
            "units": [unit.model_dump() for unit in self.units],
        }

    def public_summary(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "rule": self.rule,
            "fallback_rule": self.fallback_rule,
            "unit_count": len(self.units),
            "unit_titles": [unit.title for unit in self.units],
            "warnings": list(self.warnings),
            "units": [
                {
                    "index": unit.index,
                    "unit_type": unit.unit_type,
                    "role": unit.role,
                    "title": unit.title,
                    "content_chars": len(unit.content),
                    "source_range": unit.source_range.model_dump(),
                    "structural_path": list(unit.structural_path),
                    "raw_indexes": list(unit.raw_indexes),
                    "rule": unit.rule,
                    "metadata": dict(unit.metadata),
                }
                for unit in self.units
            ],
        }


@dataclass(frozen=True)
class _TextBlock:
    title: str | None
    text: str
    structural_path: tuple[str, ...] = ()
    metadata: dict[str, object] | None = None


CHAT_SOURCE_TYPES = {
    "hermes_chat",
    "codex_chat",
    "openclaw_chat",
    "claude_code_chat",
    "knoarbor_chat",
    "generic_chat",
}


AGENT_CHAT_SOURCE_TYPES = {"codex_chat", "openclaw_chat", "claude_code_chat"}


class SourceUnitizer:
    """Builds deterministic evidence units from normalized source documents."""

    def unitize(self, document: SourceDocument) -> SourceUnitizationResult:
        if document.source_type == "excerpt":
            return self._excerpt_units(document)
        if document.source_type in AGENT_CHAT_SOURCE_TYPES:
            return self._chat_units(document, rule="agent_task_turn_group")
        if document.source_type in CHAT_SOURCE_TYPES:
            rule: SourceUnitizationRule = "conversation_topic" if document.source_type == "hermes_chat" else "chat_turn_group"
            return self._chat_units(document, rule=rule)
        if document.source_type == "dataset":
            return self._table_units(document)
        if document.content.format == "html" or document.source_type in {"html", "web"}:
            return self._html_units(document)
        if _looks_like_code(document):
            return self._code_units(document)
        if document.source_type == "document" and document.content.sections:
            return self._section_units(document)
        if document.content.format == "markdown" or document.source_type in {"markdown", "document"}:
            return self._markdown_units(document)
        return self._paragraph_units(document)

    def _excerpt_units(self, document: SourceDocument) -> SourceUnitizationResult:
        fragments = _selected_fragments(document)
        if not fragments:
            fragments = [document.content.text]
        units = [
            SourceUnit(
                index=index,
                unit_type="excerpt",
                role="excerpt",
                title=_unit_title(fragment, fallback=f"Excerpt {index + 1}"),
                content=fragment.strip(),
                rule="selected_excerpt",
                metadata={"selection_index": index},
            )
            for index, fragment in enumerate(fragments)
            if fragment.strip()
        ]
        return _result(document, "selected_excerpt", units)

    def _chat_units(self, document: SourceDocument, *, rule: SourceUnitizationRule) -> SourceUnitizationResult:
        payload = _json_object(document.content.text)
        if payload is None:
            return self._paragraph_units(document, fallback_for=rule)
        units_key, messages = _session_messages(payload)
        if not units_key or not messages:
            return self._paragraph_units(document, fallback_for=rule)
        groups = _turn_groups(messages)
        units: list[SourceUnit] = []
        for group in groups:
            rendered = _render_chat_group(group)
            if not rendered.strip():
                continue
            raw_indexes = [session_unit_raw_index(item, offset) for offset, item in enumerate(group) if isinstance(item, dict)]
            source_range = SourceUnitRange(
                from_index=min(raw_indexes) if raw_indexes else None,
                to_index=max(raw_indexes) if raw_indexes else None,
            )
            units.append(
                SourceUnit(
                    index=len(units),
                    unit_type="conversation_turn",
                    role="user",
                    title=_chat_group_title(group, len(units)),
                    content=rendered,
                    source_range=source_range,
                    raw_indexes=raw_indexes,
                    rule=rule,
                    metadata={"units_key": units_key, "message_count": len(group)},
                )
            )
        return _result(document, rule, units or _full_source_unit(document, rule=rule, warning="empty_chat_units"), fallback_rule=None)

    def _section_units(self, document: SourceDocument) -> SourceUnitizationResult:
        units: list[SourceUnit] = []
        for index, section in enumerate(document.content.sections):
            title = str(section.get("title") or section.get("heading") or section.get("page") or f"Section {index + 1}").strip()
            text = str(section.get("content") or section.get("text") or "").strip()
            if not text:
                text = json.dumps(section, ensure_ascii=False)
            units.append(
                SourceUnit(
                    index=index,
                    unit_type="section",
                    role="note",
                    title=title,
                    content=text,
                    source_range=SourceUnitRange(from_index=index, to_index=index),
                    structural_path=[title],
                    rule="parsed_document_structure",
                    metadata=_section_metadata(section),
                )
            )
        return _result(document, "parsed_document_structure", units or _full_source_unit(document, rule="parsed_document_structure", warning="empty_sections"))

    def _markdown_units(self, document: SourceDocument) -> SourceUnitizationResult:
        blocks = _markdown_heading_blocks(document.content.text)
        if len(blocks) <= 1:
            paragraph_result = self._paragraph_units(document, fallback_for="markdown_heading")
            paragraph_result.rule = "markdown_heading"
            paragraph_result.fallback_rule = "paragraph_group"
            return paragraph_result
        units = [
            SourceUnit(
                index=index,
                unit_type="section",
                role="note",
                title=block.title,
                content=block.text,
                structural_path=list(block.structural_path),
                rule="markdown_heading",
                metadata=block.metadata or {},
            )
            for index, block in enumerate(blocks)
            if block.text.strip()
        ]
        return _result(document, "markdown_heading", units)

    def _paragraph_units(self, document: SourceDocument, *, fallback_for: SourceUnitizationRule | None = None) -> SourceUnitizationResult:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", document.content.text) if part.strip()]
        if not paragraphs:
            return _result(document, fallback_for or "full_source", _full_source_unit(document, rule=fallback_for or "full_source", warning="empty_text"), fallback_rule=fallback_for)
        groups = _paragraph_groups(paragraphs)
        units = [
            SourceUnit(
                index=index,
                unit_type="note",
                role="note",
                title=f"Paragraph group {index + 1}",
                content="\n\n".join(group),
                rule="paragraph_group",
                metadata={"paragraph_count": len(group)},
            )
            for index, group in enumerate(groups)
        ]
        return _result(document, fallback_for or "paragraph_group", units, fallback_rule="paragraph_group" if fallback_for else None)

    def _html_units(self, document: SourceDocument) -> SourceUnitizationResult:
        blocks = _html_section_blocks(document.content.text)
        if not blocks:
            return self._paragraph_units(document, fallback_for="html_section")
        units = [
            SourceUnit(
                index=index,
                unit_type="section",
                role="note",
                title=block.title,
                content=block.text,
                structural_path=list(block.structural_path),
                rule="html_section",
                metadata=block.metadata or {},
            )
            for index, block in enumerate(blocks)
        ]
        return _result(document, "html_section", units)

    def _table_units(self, document: SourceDocument) -> SourceUnitizationResult:
        units = _csv_units(document.content.text)
        if not units:
            return self._paragraph_units(document, fallback_for="table_group")
        for index, unit in enumerate(units):
            unit.index = index
        return _result(document, "table_group", units)

    def _code_units(self, document: SourceDocument) -> SourceUnitizationResult:
        blocks = _code_symbol_blocks(document.content.text)
        if not blocks:
            return self._paragraph_units(document, fallback_for="code_symbol")
        units = [
            SourceUnit(
                index=index,
                unit_type="section",
                role="note",
                title=block.title,
                content=block.text,
                structural_path=list(block.structural_path),
                rule="code_symbol",
                metadata=block.metadata or {},
            )
            for index, block in enumerate(blocks)
        ]
        return _result(document, "code_symbol", units)


def attach_source_unitization(document: SourceDocument) -> SourceDocument:
    """Attach deterministic source units to `SourceDocument.metadata`."""

    result = SourceUnitizer().unitize(document)
    return document.model_copy(update={"metadata": {**document.metadata, "source_unitization": result.summary()}})


def source_unitization_from_document(document: SourceDocument) -> SourceUnitizationResult:
    payload = document.metadata.get("source_unitization") if isinstance(document.metadata, dict) else None
    if isinstance(payload, dict):
        try:
            return SourceUnitizationResult.model_validate(payload)
        except Exception:
            pass
    return SourceUnitizer().unitize(document)


def apply_source_units_to_extract(document: SourceDocument, extract: KnowledgeExtract) -> KnowledgeExtract:
    """Make model-normalized extracts respect deterministic source units."""

    payload = document.metadata.get("source_unitization") if isinstance(document.metadata, dict) else None
    if not isinstance(payload, dict):
        return extract
    try:
        unitization = SourceUnitizationResult.model_validate(payload)
    except Exception:
        return extract
    if not unitization.units:
        return extract
    units = [
        ContentUnit(
            index=index,
            unit_type=unit.unit_type,
            role=unit.role,
            title=unit.title,
            content=unit.content,
            timestamp=None,
            is_primary=True,
            metadata={
                **unit.metadata,
                "source_unitization_rule": unit.rule,
                "source_range": unit.source_range.model_dump(),
                "raw_indexes": list(unit.raw_indexes),
                "structural_path": list(unit.structural_path),
            },
        )
        for index, unit in enumerate(unitization.units)
        if unit.content.strip()
    ]
    if not units:
        return extract
    primary_content = "\n\n".join(unit.content for unit in units if unit.content.strip())
    latest_indexes = [unit.index for unit in units]
    warnings = _dedupe([*extract.warnings, *unitization.warnings])
    return extract.model_copy(
        update={
            "content_units": units,
            "compile_context": extract.compile_context.model_copy(
                update={
                    "primary_content": primary_content,
                    "latest_unit_indexes": latest_indexes,
                }
            ),
            "attachments": list(document.content.attachments),
            "warnings": warnings,
        }
    )


def _result(
    document: SourceDocument,
    rule: SourceUnitizationRule,
    units: list[SourceUnit],
    *,
    fallback_rule: SourceUnitizationRule | None = None,
    warnings: list[str] | None = None,
) -> SourceUnitizationResult:
    resolved_warnings = list(warnings or [])
    if fallback_rule:
        resolved_warnings.append(f"unitization_fallback:{rule}->{fallback_rule}")
    if not units:
        resolved_warnings.append("unitization_empty")
    return SourceUnitizationResult(
        source_id=document.source_id,
        source_type=document.source_type,
        rule=rule,
        fallback_rule=fallback_rule,
        units=units,
        warnings=_dedupe(resolved_warnings),
    )


def _full_source_unit(document: SourceDocument, *, rule: SourceUnitizationRule, warning: str | None = None) -> list[SourceUnit]:
    metadata: dict[str, object] = {}
    if warning:
        metadata["warning"] = warning
    return [
        SourceUnit(
            index=0,
            unit_type="note",
            role="note",
            title=str(document.metadata.get("title") or document.source_id),
            content=document.content.text,
            rule=rule,
            metadata=metadata,
        )
    ]


def _selected_fragments(document: SourceDocument) -> list[str]:
    fragments = document.metadata.get("selected_fragments") if isinstance(document.metadata, dict) else None
    if isinstance(fragments, list):
        return [str(fragment).strip() for fragment in fragments if str(fragment).strip()]
    return []


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _session_messages(payload: dict[str, Any]) -> tuple[str | None, list[Any] | None]:
    for key in ("turns", "messages"):
        value = payload.get(key)
        if isinstance(value, list):
            return key, value
    return None, None


def _turn_groups(messages: list[Any]) -> list[list[Any]]:
    groups: list[list[Any]] = []
    current: list[Any] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").lower()
        if role in {"system", "developer"}:
            continue
        if role in {"tool", "function"} and not _tool_message_is_substantive(message):
            continue
        if role == "user" and current:
            groups.append(current)
            current = [message]
        else:
            current.append(message)
    if current:
        groups.append(current)
    return groups


def _tool_message_is_substantive(message: dict[str, Any]) -> bool:
    content = str(message.get("content") or "").strip()
    return bool(content) and len(content) < 4000 and not content.startswith("{")


def _render_chat_group(group: list[Any]) -> str:
    parts: list[str] = []
    for item in group:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "message").strip() or "message"
        content = str(item.get("content") or item.get("text") or "").strip()
        if not content:
            continue
        parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


def _chat_group_title(group: list[Any], index: int) -> str:
    for item in group:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() == "user":
            content = str(item.get("content") or item.get("text") or "").strip()
            if content:
                return _unit_title(content, fallback=f"Turn group {index + 1}")
    return f"Turn group {index + 1}"


def _markdown_heading_blocks(text: str) -> list[_TextBlock]:
    matches = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", text))
    if not matches:
        return [_TextBlock(title=None, text=text)]
    blocks: list[_TextBlock] = []
    if matches[0].start() > 0 and text[: matches[0].start()].strip():
        blocks.append(_TextBlock(title="Preamble", text=text[: matches[0].start()].strip(), structural_path=("Preamble",)))
    heading_stack: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        level = len(match.group(1))
        title = match.group(2).strip()
        heading_stack = [(existing_level, existing_title) for existing_level, existing_title in heading_stack if existing_level < level]
        heading_stack.append((level, title))
        block_text = text[match.start() : end].strip()
        if _heading_body_is_empty(block_text):
            continue
        blocks.append(
            _TextBlock(
                title=title,
                text=block_text,
                structural_path=tuple(stack_title for _, stack_title in heading_stack),
                metadata={"heading_level": level},
            )
        )
    return blocks or [_TextBlock(title=None, text=text)]


def _heading_body_is_empty(block_text: str) -> bool:
    lines = block_text.splitlines()
    if not lines:
        return True
    body = "\n".join(lines[1:]).strip()
    return not body


def _section_metadata(section: dict[str, Any]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for key in ("page", "page_number", "type", "kind", "bbox", "source_range"):
        value = section.get(key)
        if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
            metadata[key] = value
    return metadata


def _paragraph_groups(paragraphs: list[str], *, max_group_chars: int = 3000) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if current and current_len + paragraph_len > max_group_chars:
            groups.append(current)
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += paragraph_len
    if current:
        groups.append(current)
    return groups


def _html_section_blocks(html: str) -> list[_TextBlock]:
    matches = list(re.finditer(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", html))
    if not matches:
        text = _strip_tags(html)
        return [_TextBlock(title=None, text=text)] if text.strip() else []
    blocks: list[_TextBlock] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        title = _strip_tags(match.group(2)).strip()
        content = _strip_tags(html[match.start() : end]).strip()
        blocks.append(_TextBlock(title=title or f"HTML section {index + 1}", text=content, structural_path=(title,), metadata={"heading_level": int(match.group(1))}))
    return blocks


def _strip_tags(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _csv_units(text: str, *, group_size: int = 50) -> list[SourceUnit]:
    sample = text.strip()
    if not sample:
        return []
    try:
        rows = list(csv.reader(StringIO(sample)))
    except csv.Error:
        return []
    if len(rows) < 2 or len(rows[0]) < 2:
        return []
    header = rows[0]
    units: list[SourceUnit] = []
    for start in range(1, len(rows), group_size):
        group = rows[start : start + group_size]
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(group)
        units.append(
            SourceUnit(
                index=len(units),
                unit_type="section",
                role="note",
                title=f"Rows {start}-{start + len(group) - 1}",
                content=output.getvalue().strip(),
                source_range=SourceUnitRange(from_index=start, to_index=start + len(group) - 1),
                rule="table_group",
                metadata={"row_count": len(group), "columns": header},
            )
        )
    return units


def _looks_like_code(document: SourceDocument) -> bool:
    path = (document.origin.original_path or document.origin.raw_path or "").lower()
    if re.search(r"\.(py|ts|tsx|js|jsx|java|go|rs|cpp|c|h|hpp|swift|kt|scala|rb|php)$", path):
        return True
    return bool(re.search(r"(?m)^\s*(def|class|function|export function|const \w+\s*=|public class|func)\b", document.content.text))


def _code_symbol_blocks(text: str) -> list[_TextBlock]:
    matches = list(
        re.finditer(
            r"(?m)^(?P<indent>\s*)(def|class|function|export function|public class|func)\s+(?P<name>[A-Za-z_][\w]*)",
            text,
        )
    )
    if not matches:
        return []
    blocks: list[_TextBlock] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        name = match.group("name")
        blocks.append(_TextBlock(title=name, text=text[match.start() : end].strip(), structural_path=(name,), metadata={"symbol": name}))
    return blocks


def _unit_title(text: str, *, fallback: str) -> str:
    compact = " ".join(text.split())
    if not compact:
        return fallback
    return compact[:80]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
