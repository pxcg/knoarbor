from __future__ import annotations

from hashlib import sha1

from knoarbor.core.schemas.knowledge_atoms import KnowledgeEvidenceSpan
from knoarbor.core.schemas.knowledge_extract import ContentUnit, KnowledgeExtract
from knoarbor.core.schemas.source_digest import SourceDigest, SourceDigestAttachment, SourceDigestUnit, SourceDigestUnresolvedItem


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
        summary=_audit_summary_from_extract(extract, units),
        units=units,
        attachments=_attachments_from_extract(extract),
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


def _audit_summary_from_extract(extract: KnowledgeExtract, units: list[SourceDigestUnit]) -> str:
    source_label = extract.source.title or extract.source.source_path or extract.source.source_id or "source"
    raw_pointer = extract.source.source_path or extract.source.source_id or "not recorded"
    warning_count = len([warning for warning in extract.warnings if warning.strip()])
    return (
        f"Audit record for {source_label}. "
        f"Connector: {extract.source.source_app}. "
        f"Source units: {len(units)}. "
        f"Warnings: {warning_count}. "
        f"Raw pointer: {raw_pointer}."
    )


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


def _attachments_from_extract(extract: KnowledgeExtract) -> list[SourceDigestAttachment]:
    attachments: list[SourceDigestAttachment] = []
    for item in extract.attachments:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("relative_path") or item.get("path") or "").strip()
        if not name:
            continue
        attachment_type = str(item.get("attachment_type") or "file").strip()
        if attachment_type not in {"image", "file", "table", "other"}:
            attachment_type = "other"
        attachments.append(
            SourceDigestAttachment(
                attachment_type=attachment_type,  # type: ignore[arg-type]
                name=name,
                topic=_attachment_topic(item, name),
                description=str(item.get("description") or ""),
                path=str(item.get("path") or "") or None,
                relative_path=str(item.get("relative_path") or "") or None,
                mime_type=str(item.get("mime_type") or "") or None,
                content_hash=str(item.get("content_hash") or "") or None,
                source=str(item.get("source") or ""),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
        )
    return attachments


def _attachment_topic(item: dict[str, object], fallback_name: str) -> str:
    for key in ("topic", "title"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        caption = metadata.get("image_caption")
        if isinstance(caption, list):
            values = [str(part).strip() for part in caption if str(part).strip()]
            if values:
                return values[0]
        subtype = metadata.get("sub_type")
        if isinstance(subtype, str) and subtype.strip():
            return subtype.strip()
    return fallback_name


def _stable_hash(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()
