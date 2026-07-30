from __future__ import annotations

from pathlib import Path

from knoarbor.core.schemas.chat import (
    ChatCitation,
    ChatCitationResolution,
    ChatCitationResolveResponse,
)
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord, SourceUnitRecord
from knoarbor.storage.source_records import read_source_processing_records


class ChatCitationResolutionService:
    """Resolve answer-selected Raw spans from immutable source units on demand."""

    def resolve(
        self,
        vault_path: Path,
        citations: list[ChatCitation],
    ) -> ChatCitationResolveResponse:
        records = read_source_processing_records(vault_path)
        units = _units_by_locator(records)

        resolutions = [
            ChatCitationResolution(
                index=index,
                status="resolved" if (texts := _resolve_texts(citation, units)) else "unavailable",
                text=texts[0] if texts else None,
                texts=texts,
            )
            for index, citation in enumerate(citations)
        ]
        return ChatCitationResolveResponse(resolutions=resolutions)


def _units_by_locator(
    records: list[SourceProcessingRecord],
) -> dict[tuple[str, str], SourceUnitRecord]:
    return {
        (record.raw_revision_id, unit.source_unit_id): unit
        for record in records
        for unit in record.source_units
    }


def _resolve_texts(
    citation: ChatCitation,
    units: dict[tuple[str, str], SourceUnitRecord],
) -> list[str]:
    if (
        citation.kind != "raw_evidence"
        or not citation.raw_revision_id
        or not citation.source_unit_id
    ):
        return []
    unit = units.get((citation.raw_revision_id, citation.source_unit_id))
    if unit is None:
        return []
    content = unit.content or unit.excerpt
    unit_start = unit.char_start or 0
    ranges = (
        [(span.char_start, span.char_end) for span in citation.spans]
        if citation.spans
        else [(citation.char_start, citation.char_end)]
    )
    texts: list[str] = []
    for char_start, char_end in ranges:
        if (
            char_start is None
            or char_end is None
            or char_end <= char_start
        ):
            return []
        local_start = char_start - unit_start
        local_end = char_end - unit_start
        if not (0 <= local_start < local_end <= len(content)):
            return []
        text = content[local_start:local_end].strip()
        if not text:
            return []
        texts.append(text)
    return texts
