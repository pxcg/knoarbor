from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.storage.source_revisions import read_active_atom_batches, read_active_processing_records


KnowledgeAtomRecordType = Literal["claim", "relation", "entity", "synthesis"]


class KnowledgeAtomPageRef(BaseModel):
    path: str = Field(..., min_length=1)
    source_record_ids: list[str] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)


class KnowledgeAtomRecord(BaseModel):
    schema_version: Literal["knowledge_atom_record.v1"] = "knowledge_atom_record.v1"
    source_record_id: str
    raw_record_id: str | None = None
    raw_revision_id: str | None = None
    revision_id: str | None = None
    window_id: str | None = None
    source_unit_ids: list[str] = Field(default_factory=list)
    processing_record_id: str | None = None
    atom_id: str
    atom_type: KnowledgeAtomRecordType
    text: str
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    page_paths: list[str] = Field(default_factory=list)


def read_knowledge_atom_records(vault_path: Path) -> list[KnowledgeAtomRecord]:
    transactional = read_active_atom_batches(vault_path)
    records = {record.source_record_id: record for record in read_active_processing_records(vault_path) or []}
    return [
        record
        for batch in transactional or []
        for record in _records_from_batch(batch, _transactional_page_refs(batch, records), processing_record=records.get(batch.source_record_id))
    ]


def _transactional_page_refs(batch: KnowledgeAtomBatch, records: dict[str, Any]) -> list[KnowledgeAtomPageRef]:
    processing_record = records.get(batch.source_record_id)
    if processing_record is None:
        return []
    return [KnowledgeAtomPageRef(path=path, source_record_ids=[batch.source_record_id]) for path in processing_record.page_paths]


def _records_from_batch(
    batch: KnowledgeAtomBatch,
    page_refs: list[KnowledgeAtomPageRef],
    *,
    processing_record: Any | None = None,
) -> list[KnowledgeAtomRecord]:
    page_paths_by_atom = _page_paths_by_atom(page_refs)
    source_record_pages = _source_record_page_paths(batch.source_record_id, page_refs)
    records: list[KnowledgeAtomRecord] = []
    if batch.synthesis:
        records.append(
            KnowledgeAtomRecord(
                source_record_id=batch.source_record_id,
                atom_id=f"synthesis:{batch.source_record_id}",
                atom_type="synthesis",
                text=batch.synthesis,
                page_paths=source_record_pages,
            )
        )
    for entity in batch.entities:
        entity_evidence = [span.model_dump() for span in entity.evidence]
        records.append(
            KnowledgeAtomRecord(
                source_record_id=batch.source_record_id,
                atom_id=entity.atom_id or f"entity:{entity.name}",
                atom_type="entity",
                text=entity.name,
                payload=entity.model_dump(exclude={"evidence"}),
                evidence=entity_evidence,
                **_raw_ref_fields(entity_evidence),
                page_paths=page_paths_by_atom.get(entity.atom_id or f"entity:{entity.name}", source_record_pages),
            )
        )
    for claim in batch.claims:
        claim_evidence = [span.model_dump() for span in claim.evidence]
        records.append(
            KnowledgeAtomRecord(
                source_record_id=batch.source_record_id,
                atom_id=claim.id,
                atom_type="claim",
                text=claim.claim,
                payload=claim.model_dump(exclude={"evidence"}),
                evidence=claim_evidence,
                **_raw_ref_fields(claim_evidence),
                page_paths=page_paths_by_atom.get(claim.id, source_record_pages),
            )
        )
    for relation in batch.relations:
        relation_evidence = [span.model_dump() for span in relation.evidence]
        records.append(
            KnowledgeAtomRecord(
                source_record_id=batch.source_record_id,
                atom_id=relation.id,
                atom_type="relation",
                text=f"{relation.subject.name} {relation.predicate} {relation.object.name}",
                payload=relation.model_dump(exclude={"evidence"}),
                evidence=relation_evidence,
                **_raw_ref_fields(relation_evidence),
                page_paths=page_paths_by_atom.get(relation.id, source_record_pages),
            )
        )
    if processing_record is None:
        return records
    return [
        record.model_copy(
            update={
                "raw_record_id": record.raw_record_id or processing_record.raw_record_id,
                "raw_revision_id": record.raw_revision_id or processing_record.raw_revision_id,
                "revision_id": record.revision_id or processing_record.revision_id,
                "window_id": record.window_id or processing_record.window_id,
                "processing_record_id": record.processing_record_id or processing_record.processing_record_id,
            }
        )
        for record in records
    ]


def _page_paths_by_atom(page_refs: list[KnowledgeAtomPageRef]) -> dict[str, list[str]]:
    paths_by_atom: dict[str, list[str]] = {}
    for ref in page_refs:
        for atom_id in ref.atom_ids:
            paths_by_atom.setdefault(atom_id, [])
            if ref.path not in paths_by_atom[atom_id]:
                paths_by_atom[atom_id].append(ref.path)
    return paths_by_atom


def _source_record_page_paths(source_record_id: str, page_refs: list[KnowledgeAtomPageRef]) -> list[str]:
    paths: list[str] = []
    for ref in page_refs:
        if source_record_id in ref.source_record_ids and ref.path not in paths:
            paths.append(ref.path)
    return paths


def _raw_ref_fields(evidence_items: list[dict[str, Any]]) -> dict[str, Any]:
    raw_record_id = _first_string(item.get("raw_record_id") for item in evidence_items)
    raw_revision_id = _first_string(item.get("raw_revision_id") for item in evidence_items)
    processing_record_id = _first_string(item.get("processing_record_id") for item in evidence_items)
    revision_id = _first_string(item.get("revision_id") for item in evidence_items)
    window_id = _first_string(item.get("window_id") for item in evidence_items)
    source_unit_ids: list[str] = []
    for item in evidence_items:
        value = str(item.get("source_unit_id") or "").strip()
        if value and value not in source_unit_ids:
            source_unit_ids.append(value)
    return {
        "raw_record_id": raw_record_id,
        "raw_revision_id": raw_revision_id,
        "revision_id": revision_id,
        "window_id": window_id,
        "processing_record_id": processing_record_id,
        "source_unit_ids": source_unit_ids,
    }


def _first_string(values: object) -> str | None:
    for value in values:  # type: ignore[union-attr]
        text = str(value or "").strip()
        if text:
            return text
    return None
