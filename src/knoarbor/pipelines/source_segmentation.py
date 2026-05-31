from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from knoarbor.core.checkpoints import session_unit_raw_index
from knoarbor.core.config import IngestSegmentationConfig
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint


SegmentationMode = Literal["none", "heading", "turns", "pages", "paragraphs"]


class SourceSegmentRange(BaseModel):
    from_index: int | None = None
    to_index: int | None = None


class SourceSegment(BaseModel):
    segment_id: str
    index: int
    title: str
    content: str
    source_range: SourceSegmentRange = Field(default_factory=SourceSegmentRange)
    context_before: str = ""
    context_after: str = ""
    is_full_source: bool = False
    document: SourceDocument
    warnings: list[str] = Field(default_factory=list)


class SourceSegmentBatch(BaseModel):
    source_id: str
    source_file: str
    segmentation_mode: SegmentationMode
    segments: list[SourceSegment]
    warnings: list[str] = Field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return self.segmentation_mode != "none" or any(not segment.is_full_source for segment in self.segments)

    def summary(self) -> dict[str, object]:
        lengths = [len(segment.content) for segment in self.segments]
        return {
            "enabled": self.enabled,
            "mode": self.segmentation_mode,
            "segment_count": len(self.segments),
            "max_segment_chars": max(lengths) if lengths else 0,
            "total_segment_chars": sum(lengths),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class _Block:
    title: str
    text: str
    from_index: int | None = None
    to_index: int | None = None
    payload: dict[str, Any] | None = None
    sections: list[dict[str, Any]] | None = None
    warnings: tuple[str, ...] = ()


class SourceSegmenter:
    """Splits normalized source documents before semantic ingest."""

    def __init__(self, config: IngestSegmentationConfig | None = None) -> None:
        self.config = config or IngestSegmentationConfig()

    def segment(self, document: SourceDocument) -> SourceSegmentBatch:
        if not self.config.enabled or len(document.content.text) <= self.config.max_chars_per_segment:
            return self._single(document)

        mode, blocks = self._blocks(document)
        packed, warnings = self._pack_blocks(blocks)
        if len(packed) <= 1:
            return self._single(document, mode=mode, warnings=warnings)

        if len(packed) > self.config.max_segments_per_source:
            warnings.append(
                f"segment_count_exceeded:{len(packed)}>{self.config.max_segments_per_source}; trailing content was folded into the last segment"
            )
            packed = self._cap_segments(packed, self.config.max_segments_per_source)

        segments = [
            self._segment_from_blocks(document, mode=mode, blocks=segment_blocks, index=index, total=len(packed))
            for index, segment_blocks in enumerate(packed)
        ]
        return SourceSegmentBatch(
            source_id=document.source_id,
            source_file=document.origin.raw_path,
            segmentation_mode=mode,
            segments=segments,
            warnings=warnings,
        )

    def _single(
        self,
        document: SourceDocument,
        *,
        mode: SegmentationMode = "none",
        warnings: list[str] | None = None,
    ) -> SourceSegmentBatch:
        segment = SourceSegment(
            segment_id=f"{document.source_id}:segment:0",
            index=0,
            title=str(document.metadata.get("title") or document.source_id),
            content=document.content.text,
            source_range=SourceSegmentRange(
                from_index=document.checkpoint.from_index,
                to_index=document.checkpoint.to_index,
            ),
            is_full_source=True,
            document=document.model_copy(
                update={
                    "metadata": {
                        **document.metadata,
                        "segmentation": {
                            "enabled": False,
                            "mode": mode,
                            "segment_index": 0,
                            "segment_count": 1,
                            "is_full_source": True,
                        },
                    }
                }
            ),
            warnings=warnings or [],
        )
        return SourceSegmentBatch(
            source_id=document.source_id,
            source_file=document.origin.raw_path,
            segmentation_mode="none",
            segments=[segment],
            warnings=warnings or [],
        )

    def _blocks(self, document: SourceDocument) -> tuple[SegmentationMode, list[_Block]]:
        if document.source_type in {"hermes_chat", "codex_chat", "openclaw_chat", "claude_code_chat", "generic_chat"}:
            return "turns", self._turn_blocks(document)
        if document.content.sections and document.source_type == "document":
            return "pages", self._section_blocks(document)
        if document.content.format == "markdown":
            blocks = self._heading_blocks(document.content.text)
            return ("heading", blocks) if len(blocks) > 1 else ("paragraphs", self._paragraph_blocks(document.content.text))
        return "paragraphs", self._paragraph_blocks(document.content.text)

    def _turn_blocks(self, document: SourceDocument) -> list[_Block]:
        try:
            payload = json.loads(document.content.text)
        except json.JSONDecodeError:
            return self._paragraph_blocks(document.content.text)
        if not isinstance(payload, dict):
            return self._paragraph_blocks(document.content.text)
        units_key, units = self._session_units(payload)
        if not units_key or not units:
            return self._paragraph_blocks(document.content.text)

        groups: list[list[Any]] = []
        current: list[Any] = []
        for unit in units:
            role = str(unit.get("role") if isinstance(unit, dict) else "").lower()
            if role == "user" and current:
                groups.append(current)
                current = [unit]
            else:
                current.append(unit)
        if current:
            groups.append(current)

        blocks: list[_Block] = []
        for group in groups:
            raw_indexes = [session_unit_raw_index(unit, index) for index, unit in enumerate(group)]
            from_index = min(raw_indexes) if raw_indexes else None
            to_index = max(raw_indexes) if raw_indexes else None
            text = json.dumps(group, ensure_ascii=False, indent=2)
            title = f"turns {from_index}-{to_index}" if from_index is not None and to_index is not None else "turn group"
            segment_payload = {**payload, units_key: group}
            blocks.extend(
                self._split_oversized_block(
                    _Block(title=title, text=text, from_index=from_index, to_index=to_index, payload=segment_payload),
                    mode="turns",
                )
            )
        return blocks

    def _section_blocks(self, document: SourceDocument) -> list[_Block]:
        blocks: list[_Block] = []
        for index, section in enumerate(document.content.sections):
            title = str(section.get("title") or section.get("heading") or f"section {index + 1}")
            text = str(section.get("content") or section.get("text") or "")
            if not text.strip():
                text = json.dumps(section, ensure_ascii=False)
            blocks.extend(
                self._split_oversized_block(
                    _Block(title=title, text=text, from_index=index, to_index=index, sections=[section]),
                    mode="pages",
                )
            )
        return blocks or self._paragraph_blocks(document.content.text)

    def _heading_blocks(self, text: str) -> list[_Block]:
        matches = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", text))
        if not matches:
            return [_Block(title="Document", text=text)]
        blocks: list[_Block] = []
        if matches[0].start() > 0 and text[: matches[0].start()].strip():
            blocks.append(_Block(title="Preamble", text=text[: matches[0].start()].strip()))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            title = match.group(2).strip()
            block_text = text[match.start() : end].strip()
            blocks.extend(self._split_oversized_block(_Block(title=title, text=block_text), mode="heading"))
        return blocks

    def _paragraph_blocks(self, text: str) -> list[_Block]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not paragraphs:
            return [_Block(title="Text", text=text)]
        blocks: list[_Block] = []
        for index, paragraph in enumerate(paragraphs):
            blocks.extend(self._split_oversized_block(_Block(title=f"paragraph {index + 1}", text=paragraph), mode="paragraphs"))
        return blocks

    def _split_oversized_block(self, block: _Block, *, mode: SegmentationMode) -> list[_Block]:
        if len(block.text) <= self.config.max_chars_per_segment:
            return [block]
        warning = f"hard_split:{mode}:{block.title}"
        if block.payload is not None:
            return [
                _Block(
                    title=block.title,
                    text=block.text,
                    from_index=block.from_index,
                    to_index=block.to_index,
                    payload=block.payload,
                    sections=block.sections,
                    warnings=(*block.warnings, f"oversized_turn_group:{block.title}"),
                )
            ]
        parts = _hard_split_text(block.text, self.config.max_chars_per_segment)
        return [
            _Block(
                title=f"{block.title} part {index + 1}",
                text=part,
                from_index=block.from_index,
                to_index=block.to_index,
                payload=block.payload,
                sections=block.sections,
                warnings=(*block.warnings, warning),
            )
            for index, part in enumerate(parts)
        ]

    def _pack_blocks(self, blocks: list[_Block]) -> tuple[list[list[_Block]], list[str]]:
        warnings: list[str] = []
        segments: list[list[_Block]] = []
        current: list[_Block] = []
        current_len = 0

        for block in blocks:
            block_len = len(block.text)
            should_flush = current and (
                current_len + block_len > self.config.max_chars_per_segment
                or (current_len >= self.config.min_segment_chars and current_len + block_len > self.config.soft_chars_per_segment)
            )
            if should_flush:
                segments.append(current)
                current = []
                current_len = 0
            current.append(block)
            current_len += block_len
            warnings.extend(block.warnings)
        if current:
            segments.append(current)
        return segments, _dedupe(warnings)

    def _cap_segments(self, segments: list[list[_Block]], limit: int) -> list[list[_Block]]:
        if len(segments) <= limit:
            return segments
        kept = segments[: limit - 1]
        tail: list[_Block] = []
        for segment in segments[limit - 1 :]:
            tail.extend(segment)
        kept.append(tail)
        return kept

    def _segment_from_blocks(
        self,
        document: SourceDocument,
        *,
        mode: SegmentationMode,
        blocks: list[_Block],
        index: int,
        total: int,
    ) -> SourceSegment:
        content = "\n\n".join(block.text for block in blocks).strip()
        title = _segment_title(blocks, index)
        from_values = [block.from_index for block in blocks if block.from_index is not None]
        to_values = [block.to_index for block in blocks if block.to_index is not None]
        content_start = document.content.text.find(content)
        if content_start >= 0:
            context_before = document.content.text[max(0, content_start - self.config.overlap_chars) : content_start]
            content_end = content_start + len(content)
            context_after = document.content.text[content_end : content_end + self.config.overlap_chars]
        else:
            context_before = ""
            context_after = ""
        segment_document = self._segment_document(document, mode=mode, blocks=blocks, content=content, index=index, total=total, title=title)
        return SourceSegment(
            segment_id=f"{document.source_id}:segment:{index}",
            index=index,
            title=title,
            content=content,
            source_range=SourceSegmentRange(
                from_index=min(from_values) if from_values else document.checkpoint.from_index,
                to_index=max(to_values) if to_values else document.checkpoint.to_index,
            ),
            context_before=context_before,
            context_after=context_after,
            is_full_source=False,
            document=segment_document,
            warnings=_dedupe([warning for block in blocks for warning in block.warnings]),
        )

    def _segment_document(
        self,
        document: SourceDocument,
        *,
        mode: SegmentationMode,
        blocks: list[_Block],
        content: str,
        index: int,
        total: int,
        title: str,
    ) -> SourceDocument:
        payload = self._merged_payload(blocks)
        sections = [section for block in blocks for section in (block.sections or [])]
        content_format = document.content.format
        text = content
        if payload is not None:
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            content_format = "json"
        source_id = document.source_id
        metadata = {
            **document.metadata,
            "segmentation": {
                "enabled": True,
                "mode": mode,
                "segment_id": f"{document.source_id}:segment:{index}",
                "segment_index": index,
                "segment_count": total,
                "segment_title": title,
                "is_full_source": False,
                "guidance": (
                    "This is one segment of a larger source. Preserve stable page boundaries, avoid thin fragment pages, "
                    "and do not create duplicate source digest pages for every segment."
                ),
            },
        }
        return document.model_copy(
            update={
                "source_id": source_id,
                "content": SourceContent(format=content_format, text=text, sections=sections),
                "metadata": metadata,
                "fingerprint": SourceFingerprint(
                    content_hash=f"{document.fingerprint.content_hash}-s{index}",
                    connector_version=document.fingerprint.connector_version,
                    parser_version=document.fingerprint.parser_version,
                ),
            }
        )

    def _merged_payload(self, blocks: list[_Block]) -> dict[str, Any] | None:
        payloads = [block.payload for block in blocks if block.payload is not None]
        if not payloads:
            return None
        base = dict(payloads[0])
        units_key, _ = self._session_units(base)
        if not units_key:
            return base
        units: list[Any] = []
        for payload in payloads:
            value = payload.get(units_key)
            if isinstance(value, list):
                units.extend(value)
        base[units_key] = units
        return base

    def _session_units(self, payload: dict[str, Any]) -> tuple[str | None, list[Any] | None]:
        for key in ("messages", "turns"):
            value = payload.get(key)
            if isinstance(value, list):
                return key, value
        return None, None


def _segment_title(blocks: list[_Block], index: int) -> str:
    if not blocks:
        return f"Segment {index + 1}"
    if len(blocks) == 1:
        return blocks[0].title
    return f"{blocks[0].title} - {blocks[-1].title}"


def _hard_split_text(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    remaining = text.strip()
    while len(remaining) > max_chars:
        split_at = remaining.rfind("\n\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = remaining.rfind("\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
