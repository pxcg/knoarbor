from __future__ import annotations

import json
from pathlib import Path

from knoarbor.core.hashing import content_hash
from knoarbor.core.knowledge_evidence import map_knowledge_evidence
from knoarbor.core.markdown import inline_text
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeEvidenceSpan
from knoarbor.core.schemas.raw_evidence import OriginalSourceRecord, RawEvidenceRecord, SourceProcessingRecord, SourceUnitRecord
from knoarbor.core.schemas.source_record import SourceRecord
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.source_unitization import source_unitization_from_document
from knoarbor.storage.source_revisions import read_active_processing_records


def source_identity(document: SourceDocument, *, source_path: str = "") -> tuple[str, str]:
    connector = document.origin.connector or document.source_type or "source"
    raw_pointer = source_path or document.origin.raw_path or document.source_id
    raw_seed = "|".join([str(connector), str(raw_pointer), document.source_id])
    raw_record_id = f"raw:{_stable_hash(raw_seed)}"
    return raw_record_id, raw_revision_identity(raw_record_id, document)


def raw_revision_identity(raw_record_id: str, document: SourceDocument) -> str:
    revision_seed = "|".join([raw_record_id, document.fingerprint.content_hash, document.schema_version])
    return f"rawrev:{_stable_hash(revision_seed)}"


def source_unit_id(
    raw_revision_id: str, *, unit_index: int, rule: str = "", structural_path: list[str] | None = None, content: str = ""
) -> str:
    seed = json.dumps(
        {
            "raw_revision_id": raw_revision_id,
            "unit_index": unit_index,
            "rule": rule,
            "structural_path": structural_path or [],
            "content_hash": _stable_hash(content),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"unit:{_stable_hash(seed)}"


def processing_record_id(raw_revision_id: str, source_record_id: str, *, ingest_profile: str = "", scope: str = "full_source") -> str:
    return f"spr:{_stable_hash(raw_revision_id, source_record_id, ingest_profile, scope)}"


def build_source_processing_record(
    document: SourceDocument,
    source_record: SourceRecord,
    *,
    source_path: str,
    ingest_profile: str = "",
    atom_batch: KnowledgeAtomBatch | None = None,
    page_paths: list[str] | None = None,
    run_id: str = "",
    warnings: list[str] | None = None,
) -> SourceProcessingRecord:
    raw_record_id, raw_revision_id = source_identity(document, source_path=source_path)
    original = OriginalSourceRecord(
        raw_record_id=raw_record_id,
        raw_revision_id=raw_revision_id,
        source_id=document.source_id,
        source_type=document.source_type,
        connector=document.origin.connector or "",
        raw_path=source_path or document.origin.raw_path,
        title=_document_title(document, source_record),
        content_hash=document.fingerprint.content_hash,
        normalized_content_hash=_stable_hash(document.content.text or ""),
        metadata={
            "origin": document.origin.model_dump(),
            "content_format": document.content.format,
        },
    )
    source_units = _source_unit_records(document, source_record, original)
    atom_ids = _atom_ids(atom_batch)
    return SourceProcessingRecord(
        processing_record_id=processing_record_id(raw_revision_id, source_record.record_id, ingest_profile=ingest_profile),
        raw_record_id=raw_record_id,
        raw_revision_id=raw_revision_id,
        source_record_id=source_record.record_id,
        run_id=run_id,
        ingest_profile=ingest_profile,
        source=original,
        source_units=source_units,
        attachments=list(source_record.attachments),
        atom_ids=atom_ids,
        page_paths=page_paths or [],
        decisions={
            "contribution_count": len(source_record.contribution_map),
            "unresolved_count": len(source_record.unresolved_items),
            "attachments": len(source_record.attachments),
        },
        warnings=[*source_record.warnings, *(warnings or [])],
        metadata={
            "source_record_summary": source_record.summary_counts(),
            "source_focus": source_record.source_focus,
        },
    )


def read_source_processing_records(vault_path: Path) -> list[SourceProcessingRecord]:
    transactional = read_active_processing_records(vault_path)
    return transactional or []


def read_raw_evidence_records(vault_path: Path) -> list[RawEvidenceRecord]:
    transactional_records = read_active_processing_records(vault_path)
    return [evidence for record in transactional_records or [] for evidence in raw_evidence_records_from_processing_record(record)]


def raw_evidence_records_from_processing_record(record: SourceProcessingRecord) -> list[RawEvidenceRecord]:
    output: list[RawEvidenceRecord] = []
    for unit in record.source_units:
        excerpt = unit.excerpt or unit.content
        evidence_id = f"ev:{_stable_hash(record.processing_record_id, unit.source_unit_id, unit.excerpt_hash or excerpt)}"
        output.append(
            RawEvidenceRecord(
                evidence_id=evidence_id,
                raw_record_id=record.raw_record_id,
                raw_revision_id=record.raw_revision_id,
                revision_id=record.revision_id,
                window_id=record.window_id,
                source_unit_id=unit.source_unit_id,
                source_record_id=record.source_record_id,
                processing_record_id=record.processing_record_id,
                source_path=unit.source_path or record.source.raw_path,
                unit_index=unit.unit_index,
                unit_type=unit.unit_type,
                title=unit.title,
                excerpt=excerpt,
                content=unit.content,
                excerpt_hash=unit.excerpt_hash,
                char_start=unit.char_start,
                char_end=unit.char_end,
                structural_path=list(unit.structural_path),
                raw_indexes=list(unit.raw_indexes),
                locator_atom_ids=list(record.atom_ids),
                locator_page_paths=list(record.page_paths),
                metadata={"ingest_profile": record.ingest_profile},
            )
        )
    return output


def enrich_evidence_span(span: KnowledgeEvidenceSpan, record: SourceProcessingRecord) -> KnowledgeEvidenceSpan:
    unit = _unit_for_span(span, record)
    if unit is None:
        raise ValueError(f"Evidence for source record {record.source_record_id} does not reference a published source unit.")
    return span.model_copy(
        update={
            "raw_record_id": record.raw_record_id,
            "raw_revision_id": record.raw_revision_id,
            "revision_id": record.revision_id,
            "window_id": record.window_id,
            "source_unit_id": unit.source_unit_id,
            "processing_record_id": record.processing_record_id,
            "source_path": span.source_path or unit.source_path,
            "excerpt_hash": span.excerpt_hash or unit.excerpt_hash,
            "char_start": span.char_start if span.char_start is not None else unit.char_start,
            "char_end": span.char_end if span.char_end is not None else unit.char_end,
        }
    )


def enrich_atom_batch_evidence(batch: KnowledgeAtomBatch, record: SourceProcessingRecord) -> KnowledgeAtomBatch:
    return map_knowledge_evidence(batch, lambda span: enrich_evidence_span(span, record))


def _source_unit_records(document: SourceDocument, source_record: SourceRecord, original: OriginalSourceRecord) -> list[SourceUnitRecord]:
    source_path = source_record.raw_source or source_record.source.source_path or original.raw_path
    if source_record.units:
        records: list[SourceUnitRecord] = []
        for unit in source_record.units:
            content = unit.evidence.excerpt.strip()
            if not content:
                continue
            structural_path = unit.metadata.get("structural_path") if isinstance(unit.metadata, dict) else None
            raw_indexes = unit.metadata.get("raw_indexes") if isinstance(unit.metadata, dict) else None
            source_range = unit.metadata.get("source_range") if isinstance(unit.metadata, dict) else None
            records.append(
                SourceUnitRecord(
                    source_unit_id=source_unit_id(
                        original.raw_revision_id,
                        unit_index=unit.index,
                        rule=str(unit.metadata.get("source_unitization_rule") or unit.unit_type)
                        if isinstance(unit.metadata, dict)
                        else unit.unit_type,
                        structural_path=list(structural_path) if isinstance(structural_path, list) else [],
                        content=content,
                    ),
                    raw_record_id=original.raw_record_id,
                    raw_revision_id=original.raw_revision_id,
                    unit_index=unit.index,
                    unit_type=unit.unit_type,
                    role=str(unit.metadata.get("role") or "note") if isinstance(unit.metadata, dict) else "note",
                    title=unit.title or "",
                    content=content,
                    excerpt=content,
                    excerpt_hash=unit.evidence.excerpt_hash or _stable_hash(source_path, unit.index, content),
                    char_start=unit.evidence.char_start if unit.evidence.char_start is not None else 0,
                    char_end=unit.evidence.char_end if unit.evidence.char_end is not None else len(content),
                    structural_path=list(structural_path) if isinstance(structural_path, list) else [],
                    raw_indexes=[int(item) for item in raw_indexes]
                    if isinstance(raw_indexes, list) and all(isinstance(item, int) for item in raw_indexes)
                    else [],
                    source_range=source_range if isinstance(source_range, dict) else {},
                    unitization_rule=str(unit.metadata.get("source_unitization_rule") or "") if isinstance(unit.metadata, dict) else "",
                    source_path=source_path,
                    metadata=dict(unit.metadata),
                )
            )
        if records:
            return records

    unitization = source_unitization_from_document(document)
    record_units_by_index = {unit.index: unit for unit in source_record.units}
    records: list[SourceUnitRecord] = []
    for unit in unitization.units:
        content = unit.content.strip()
        if not content:
            continue
        record_unit = record_units_by_index.get(unit.index)
        excerpt = record_unit.evidence.excerpt if record_unit else content
        unit_hash = _stable_hash(source_path, unit.index, content)
        records.append(
            SourceUnitRecord(
                source_unit_id=source_unit_id(
                    original.raw_revision_id,
                    unit_index=unit.index,
                    rule=unit.rule,
                    structural_path=list(unit.structural_path),
                    content=content,
                ),
                raw_record_id=original.raw_record_id,
                raw_revision_id=original.raw_revision_id,
                unit_index=unit.index,
                unit_type=unit.unit_type,
                role=unit.role,
                title=unit.title or "",
                content=content,
                excerpt=excerpt,
                excerpt_hash=(record_unit.evidence.excerpt_hash if record_unit else None) or unit_hash,
                char_start=record_unit.evidence.char_start if record_unit else 0,
                char_end=record_unit.evidence.char_end if record_unit else len(content),
                structural_path=list(unit.structural_path),
                raw_indexes=list(unit.raw_indexes),
                source_range=unit.source_range.model_dump(),
                unitization_rule=unit.rule,
                source_path=source_path,
                metadata=dict(unit.metadata),
            )
        )
    if records:
        return records
    source_text = document.content.text.strip()
    if not source_text:
        return []
    return [
        SourceUnitRecord(
            source_unit_id=source_unit_id(original.raw_revision_id, unit_index=0, rule="full_source", content=source_text),
            raw_record_id=original.raw_record_id,
            raw_revision_id=original.raw_revision_id,
            unit_index=0,
            unit_type="note",
            role="note",
            title=original.title,
            content=source_text,
            excerpt=source_text,
            excerpt_hash=_stable_hash(source_path, source_text),
            char_start=0,
            char_end=len(source_text),
            unitization_rule="full_source",
            source_path=source_path,
        )
    ]


def _unit_for_span(span: KnowledgeEvidenceSpan, record: SourceProcessingRecord) -> SourceUnitRecord | None:
    if span.source_unit_id:
        for unit in record.source_units:
            if unit.source_unit_id == span.source_unit_id:
                return unit
    if span.source_unit_index is not None:
        for unit in record.source_units:
            if unit.unit_index == span.source_unit_index:
                return unit
    return None


def _atom_ids(batch: KnowledgeAtomBatch | None) -> list[str]:
    if batch is None:
        return []
    ids = [
        *[entity.atom_id or f"entity:{entity.name}" for entity in batch.entities],
        *[claim.id for claim in batch.claims],
        *[relation.id for relation in batch.relations],
    ]
    output: list[str] = []
    for item in ids:
        if item and item not in output:
            output.append(item)
    return output


def _document_title(document: SourceDocument, source_record: SourceRecord) -> str:
    for value in (
        document.metadata.get("title") if isinstance(document.metadata, dict) else None,
        source_record.source.title,
        source_record.source_focus,
        Path(document.origin.raw_path or "").stem,
        document.source_id,
    ):
        text = str(value or "").strip()
        if text:
            return inline_text(text)
    return document.source_id


def _stable_hash(*parts: object) -> str:
    return content_hash("source_record", json.dumps([str(part) for part in parts], ensure_ascii=False, sort_keys=True))
