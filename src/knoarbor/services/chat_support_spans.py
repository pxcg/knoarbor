from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from knoarbor.core.schemas.chat import ChatCitation


@dataclass(frozen=True)
class ChatSupportSpan:
    support_span_id: str
    evidence_id: str
    text: str
    char_start: int
    char_end: int
    source_unit_id: str | None
    raw_revision_id: str | None
    source_path: str | None
    title: str | None
    document_title: str | None
    vault_id: str | None
    vault_name: str | None
    vault_path: str | None

    def model_payload(self) -> dict[str, object]:
        return {
            "support_span_id": self.support_span_id,
            "evidence_id": self.evidence_id,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }

    def answer_model_payload(self) -> dict[str, object]:
        """Expose answer semantics without code-owned locator offsets."""

        return {
            "support_span_id": self.support_span_id,
            "evidence_id": self.evidence_id,
            "text": self.text,
        }

    def citation(self) -> ChatCitation:
        return ChatCitation(
            kind="raw_evidence",
            role="source",
            path=self.source_path,
            title=self.title or self.source_unit_id or "Source evidence",
            vault_id=self.vault_id,
            vault_name=self.vault_name,
            vault_path=self.vault_path,
            evidence_id=self.evidence_id,
            raw_revision_id=self.raw_revision_id,
            source_unit_id=self.source_unit_id,
            char_start=self.char_start,
            char_end=self.char_end,
            reason="Deterministic Raw support for the answer.",
        )


def build_support_spans(item: dict[str, Any], *, evidence_index: int) -> list[ChatSupportSpan]:
    """Build deterministic citeable spans from exact Query evidence segments."""

    evidence_id = str(item.get("evidence_id") or "").strip()
    if not evidence_id:
        return []
    segments = _evidence_segments(item)
    if not segments:
        content = str(item.get("content") or item.get("excerpt") or "")
        unit_start = int(item.get("source_unit_char_start") or 0)
        segments = [(content, unit_start)]
    spans: list[ChatSupportSpan] = []
    for content, segment_start in segments:
        for local_start, local_end in _citeable_ranges(content):
            ordinal = len(spans) + 1
            spans.append(
                ChatSupportSpan(
                    support_span_id=f"sp_{evidence_index + 1}_{ordinal}",
                    evidence_id=evidence_id,
                    text=content[local_start:local_end],
                    char_start=segment_start + local_start,
                    char_end=segment_start + local_end,
                    source_unit_id=_optional_text(item.get("source_unit_id")),
                    raw_revision_id=_optional_text(item.get("raw_revision_id")),
                    source_path=_optional_text(item.get("source_path")),
                    title=_optional_text(item.get("title")),
                    document_title=_optional_text(item.get("document_title")),
                    vault_id=_optional_text(item.get("vault_id")),
                    vault_name=_optional_text(item.get("vault_name")),
                    vault_path=_optional_text(item.get("vault_path")),
                )
            )
    return spans


def support_span_catalog(raw_evidence: list[dict[str, Any]]) -> list[ChatSupportSpan]:
    return [
        span
        for evidence_index, item in enumerate(raw_evidence)
        for span in build_support_spans(item, evidence_index=evidence_index)
    ]


def _citeable_ranges(content: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for line_match in re.finditer(r"[^\r\n]+", content):
        raw_line = line_match.group(0)
        left = len(raw_line) - len(raw_line.lstrip())
        right = len(raw_line.rstrip())
        if left >= right:
            continue
        line_start = line_match.start() + left
        line_text = content[line_start:line_match.start() + right]
        if _is_markdown_structural_line(line_text):
            ranges.append((line_start, line_start + len(line_text)))
            continue
        sentence_ranges = _sentence_ranges(line_text)
        ranges.extend((line_start + start, line_start + end) for start, end in sentence_ranges)
    return ranges


def _evidence_segments(item: dict[str, Any]) -> list[tuple[str, int]]:
    value = item.get("evidence_segments")
    if not isinstance(value, list):
        return []
    output: list[tuple[str, int]] = []
    for segment in value:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "")
        start = segment.get("char_start")
        end = segment.get("char_end")
        if (
            text
            and isinstance(start, int)
            and isinstance(end, int)
            and start < end
            and len(text) == end - start
        ):
            output.append((text, start))
    return output


def _is_markdown_structural_line(line: str) -> bool:
    return bool(re.match(r"^(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s|```|\|)", line))


def _sentence_ranges(line: str) -> list[tuple[int, int]]:
    output: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"[。！？!?]|\.(?=\s|$)", line):
        end = match.end()
        if line[start:end].strip():
            leading = len(line[start:end]) - len(line[start:end].lstrip())
            output.append((start + leading, end))
        start = end
    if line[start:].strip():
        leading = len(line[start:]) - len(line[start:].lstrip())
        output.append((start + leading, len(line.rstrip())))
    return output


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
