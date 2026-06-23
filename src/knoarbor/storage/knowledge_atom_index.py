from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.runtime import vault_write_lock
from knoarbor.storage.wiki_index import machine_index_dir


KNOWLEDGE_ATOM_INDEX_SCHEMA = "knowledge_atom_index.v1"
KNOWLEDGE_ATOM_INDEX_PATH = "knowledge_atoms.jsonl"

KnowledgeAtomRecordType = Literal["claim", "relation", "entity", "evidence"]


class KnowledgeAtomPageRef(BaseModel):
    path: str = Field(..., min_length=1)
    source_digest_ids: list[str] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)


class KnowledgeAtomRecord(BaseModel):
    schema_version: Literal["knowledge_atom_record.v1"] = "knowledge_atom_record.v1"
    source_digest_id: str
    atom_id: str
    atom_type: KnowledgeAtomRecordType
    text: str
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    page_paths: list[str] = Field(default_factory=list)


def knowledge_atom_index_path(vault_path: Path) -> Path:
    return machine_index_dir(vault_path) / KNOWLEDGE_ATOM_INDEX_PATH


def upsert_knowledge_atom_batch(vault_path: Path, batch: KnowledgeAtomBatch, page_refs: list[KnowledgeAtomPageRef]) -> Path:
    return upsert_knowledge_atom_batches(vault_path, [batch], page_refs)


def upsert_knowledge_atom_batches(vault_path: Path, batches: list[KnowledgeAtomBatch], page_refs: list[KnowledgeAtomPageRef]) -> Path:
    path = knowledge_atom_index_path(vault_path)
    source_digest_ids = {batch.source_digest_id for batch in batches}
    records = [record for batch in batches for record in _records_from_batch(batch, page_refs)]
    with vault_write_lock(vault_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = [record for record in read_knowledge_atom_records(vault_path) if record.source_digest_id not in source_digest_ids]
        merged = [*existing, *records]
        with path.open("w", encoding="utf-8") as handle:
            for record in merged:
                handle.write(json.dumps(record.model_dump(), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_knowledge_atom_records(vault_path: Path) -> list[KnowledgeAtomRecord]:
    path = knowledge_atom_index_path(vault_path)
    if not path.exists():
        return []
    records: list[KnowledgeAtomRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
                records.append(KnowledgeAtomRecord.model_validate(payload))
            except (json.JSONDecodeError, ValueError):
                continue
    return records


def _records_from_batch(batch: KnowledgeAtomBatch, page_refs: list[KnowledgeAtomPageRef]) -> list[KnowledgeAtomRecord]:
    page_paths_by_atom = _page_paths_by_atom(page_refs)
    source_digest_pages = _source_digest_page_paths(batch.source_digest_id, page_refs)
    records: list[KnowledgeAtomRecord] = []
    for entity in batch.entities:
        records.append(
            KnowledgeAtomRecord(
                source_digest_id=batch.source_digest_id,
                atom_id=entity.atom_id or f"entity:{entity.name}",
                atom_type="entity",
                text=entity.name,
                payload=entity.model_dump(),
                evidence=[],
                page_paths=page_paths_by_atom.get(entity.atom_id or f"entity:{entity.name}", source_digest_pages),
            )
        )
    for claim in batch.claims:
        records.append(
            KnowledgeAtomRecord(
                source_digest_id=batch.source_digest_id,
                atom_id=claim.id,
                atom_type="claim",
                text=claim.claim,
                payload=claim.model_dump(exclude={"evidence"}),
                evidence=[span.model_dump() for span in claim.evidence],
                page_paths=page_paths_by_atom.get(claim.id, source_digest_pages),
            )
        )
    for relation in batch.relations:
        records.append(
            KnowledgeAtomRecord(
                source_digest_id=batch.source_digest_id,
                atom_id=relation.id,
                atom_type="relation",
                text=f"{relation.subject.name} {relation.predicate} {relation.object.name}",
                payload=relation.model_dump(exclude={"evidence"}),
                evidence=[span.model_dump() for span in relation.evidence],
                page_paths=page_paths_by_atom.get(relation.id, source_digest_pages),
            )
        )
    for index, evidence in enumerate(batch.evidence):
        evidence_id = evidence.excerpt_hash or f"evidence:{batch.source_digest_id}:{index}"
        records.append(
            KnowledgeAtomRecord(
                source_digest_id=batch.source_digest_id,
                atom_id=evidence_id,
                atom_type="evidence",
                text=evidence.excerpt,
                payload=evidence.model_dump(),
                evidence=[evidence.model_dump()],
                page_paths=source_digest_pages,
            )
        )
    return records


def _page_paths_by_atom(page_refs: list[KnowledgeAtomPageRef]) -> dict[str, list[str]]:
    paths_by_atom: dict[str, list[str]] = {}
    for ref in page_refs:
        for atom_id in ref.atom_ids:
            paths_by_atom.setdefault(atom_id, [])
            if ref.path not in paths_by_atom[atom_id]:
                paths_by_atom[atom_id].append(ref.path)
    return paths_by_atom


def _source_digest_page_paths(source_digest_id: str, page_refs: list[KnowledgeAtomPageRef]) -> list[str]:
    paths: list[str] = []
    for ref in page_refs:
        if source_digest_id in ref.source_digest_ids and ref.path not in paths:
            paths.append(ref.path)
    return paths
