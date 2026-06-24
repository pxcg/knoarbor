from __future__ import annotations

import hashlib
from collections.abc import Iterable
import re

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeAtomObject


def normalize_knowledge_atom_batch(batch: KnowledgeAtomBatch) -> KnowledgeAtomBatch:
    """Close source-local atom references before planning or write gating.

    Entity references are model-authored, but their closure is deterministic:
    every entity named by a claim or relation should exist in the batch entity
    list so downstream graph/index stages have stable nodes.
    """

    declared: dict[str, KnowledgeAtomObject] = {_object_key(entity.name): entity for entity in batch.entities}
    entities = list(batch.entities)
    warnings = list(batch.warnings)

    for name in _referenced_entity_names(batch):
        key = _object_key(name)
        if key in declared:
            continue
        entity = KnowledgeAtomObject(
            object_type="knowledge_object",
            name=name,
            atom_id=_entity_atom_id(name, existing={item.atom_id or "" for item in entities}),
        )
        declared[key] = entity
        entities.append(entity)
        warnings.append(f"auto_declared_entity:{name}")

    if len(entities) == len(batch.entities) and warnings == batch.warnings:
        return batch
    return batch.model_copy(update={"entities": entities, "warnings": warnings})


def _referenced_entity_names(batch: KnowledgeAtomBatch) -> list[str]:
    names: list[str] = []
    for claim in batch.claims:
        names.extend(claim.entity_names)
    for relation in batch.relations:
        names.append(relation.subject.name)
        names.append(relation.object.name)
    return _unique(name for name in names if name.strip())


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        key = _object_key(text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _entity_atom_id(name: str, *, existing: set[str]) -> str:
    base = "entity_" + re.sub(r"[^0-9A-Za-z]+", "_", name.casefold()).strip("_")
    if not base or base == "entity_":
        base = "entity_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    atom_id = base
    counter = 2
    while atom_id in existing:
        atom_id = f"{base}_{counter}"
        counter += 1
    return atom_id


def _object_key(value: str) -> str:
    return " ".join(value.casefold().split())
