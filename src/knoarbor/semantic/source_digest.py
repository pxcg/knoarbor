from __future__ import annotations

from hashlib import sha1

from knoarbor.core.schemas.knowledge_atoms import KnowledgeEvidenceSpan
from knoarbor.core.schemas.knowledge_extract import ContentUnit, KnowledgeExtract
from knoarbor.core.schemas.source_digest import SourceDigest, SourceDigestUnit, SourceDigestUnresolvedItem


def build_source_digest_from_extract(extract: KnowledgeExtract, *, digest_id: str | None = None) -> SourceDigest:
    """Project normalized source units into the source digest audit contract."""

    resolved_digest_id = digest_id or _digest_id(extract)
    units = [
        SourceDigestUnit(
            index=unit.index,
            unit_type=unit.unit_type,
            title=unit.title,
            summary=_unit_summary(unit),
            evidence=KnowledgeEvidenceSpan(
                source_digest_id=resolved_digest_id,
                source_path=extract.source.source_path,
                source_unit_index=unit.index,
                excerpt=unit.content,
                excerpt_hash=_stable_hash(unit.content),
            ),
            metadata=dict(unit.metadata),
        )
        for unit in extract.content_units
        if unit.content.strip()
    ]
    content_fingerprint = _extract_content_hash(extract)
    return SourceDigest(
        digest_id=resolved_digest_id,
        source=extract.source,
        raw_source=extract.source.source_path,
        content_hash=content_fingerprint,
        source_focus=extract.source.title,
        summary=_summary_from_extract(extract),
        units=units,
        unresolved_items=_unresolved_items_from_extract(extract, units),
        confidence=extract.confidence,
        warnings=list(extract.warnings),
    )


def _digest_id(extract: KnowledgeExtract) -> str:
    seed = "|".join(
        [
            extract.source.source_app,
            extract.source.source_id or "",
            extract.source.source_path or "",
            extract.source.title,
        ]
    )
    return "sd_" + _stable_hash(seed)[:16]


def _unit_summary(unit: ContentUnit) -> str:
    if unit.title:
        return unit.title
    text = " ".join(unit.content.split())
    return text[:160]


def _summary_from_extract(extract: KnowledgeExtract) -> str:
    primary = " ".join(extract.compile_context.primary_content.split())
    if primary:
        return primary[:500]
    unit_text = " ".join(" ".join(unit.content.split()) for unit in extract.content_units[:3])
    return unit_text[:500]


def _extract_content_hash(extract: KnowledgeExtract) -> str:
    seed = "\n\n".join(unit.content for unit in extract.content_units if unit.content.strip())
    if not seed:
        seed = extract.compile_context.primary_content or extract.source.source_path or extract.source.title
    return _stable_hash(seed)


def _unresolved_items_from_extract(extract: KnowledgeExtract, units: list[SourceDigestUnit]) -> list[SourceDigestUnresolvedItem]:
    unit_ids = [f"U{unit.index + 1}" for unit in units[:1]]
    items: list[SourceDigestUnresolvedItem] = []
    for index, warning in enumerate(extract.warnings, start=1):
        text = warning.strip()
        if not text:
            continue
        items.append(
            SourceDigestUnresolvedItem(
                item_id=f"W{index}",
                item_type="warning",
                reason=text,
                evidence_unit_ids=unit_ids,
            )
        )
    return items


def _stable_hash(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()
