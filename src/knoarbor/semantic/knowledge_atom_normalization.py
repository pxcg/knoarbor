from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import re

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeAtomObject, KnowledgeClaim, KnowledgeRelation


def normalize_knowledge_atom_batch(batch: KnowledgeAtomBatch) -> KnowledgeAtomBatch:
    """Close source-local atom references before planning or write gating.

    Entity references are model-authored, but their closure is deterministic:
    every entity named by a claim or relation should exist in the batch entity
    list so downstream graph/index stages have stable nodes.
    """

    entities = _canonical_entities(batch.entities)
    declared: dict[str, KnowledgeAtomObject] = {}
    alias_map: dict[str, str] = {}
    for entity in entities:
        declared[_object_key(entity.name)] = entity
        alias_map[_object_key(entity.name)] = entity.name
        for alias in entity.aliases:
            alias_map[_object_key(alias)] = entity.name
    evidence_by_entity = _entity_evidence_refs(batch)

    for name in _referenced_entity_names(batch):
        key = _object_key(name)
        if key in declared:
            continue
        if key in alias_map:
            continue
        entity = KnowledgeAtomObject(
            object_type="knowledge_object",
            name=name,
            atom_id=_entity_atom_id(name, existing={item.atom_id or "" for item in entities}),
            evidence=evidence_by_entity.get(key, []),
        )
        declared[key] = entity
        alias_map[key] = entity.name
        entities.append(entity)

    entities = [_entity_with_inferred_evidence(entity, evidence_by_entity) for entity in entities]

    claims = [_canonical_claim(claim, alias_map) for claim in batch.claims]
    evidence_by_claim_id = {claim.id: claim.evidence for claim in claims}
    relations = [_canonical_relation(relation, alias_map, evidence_by_claim_id) for relation in batch.relations]

    if entities == batch.entities and claims == batch.claims and relations == batch.relations:
        return batch
    return batch.model_copy(update={"entities": entities, "claims": claims, "relations": relations})


@dataclass
class _EntityGroup:
    canonical: KnowledgeAtomObject
    aliases: list[str]


def _canonical_entities(entities: list[KnowledgeAtomObject]) -> list[KnowledgeAtomObject]:
    entities = _remove_aliases_conflicting_with_declared_names(entities)
    groups: list[_EntityGroup] = []
    group_by_key: dict[str, _EntityGroup] = {}
    for entity in entities:
        keys = _entity_keys(entity)
        matched_groups = []
        for key in keys:
            group = group_by_key.get(key)
            if group is not None and group not in matched_groups:
                matched_groups.append(group)
        group = matched_groups[0] if matched_groups else None
        if group is None:
            group = _EntityGroup(canonical=entity, aliases=[])
            groups.append(group)
        for duplicate in matched_groups[1:]:
            group.aliases = _merge_aliases(group.aliases, [duplicate.canonical.name, *duplicate.aliases])
            group.canonical = _preferred_entity(group.canonical, duplicate.canonical)
            if duplicate in groups:
                groups.remove(duplicate)
        names = [entity.name, *entity.aliases]
        group.aliases = _merge_aliases(group.aliases, names)
        group.canonical = _preferred_entity(group.canonical, entity)
        for key in _dedupe_keys([*_entity_keys(group.canonical), *(_object_key(alias) for alias in group.aliases)]):
            group_by_key[key] = group
    normalized: list[KnowledgeAtomObject] = []
    used_ids: set[str] = set()
    for group in groups:
        aliases = [alias for alias in group.aliases if _object_key(alias) != _object_key(group.canonical.name)]
        atom_id = group.canonical.atom_id or _entity_atom_id(group.canonical.name, existing=used_ids)
        if atom_id in used_ids:
            atom_id = _entity_atom_id(group.canonical.name, existing=used_ids)
        used_ids.add(atom_id)
        normalized.append(group.canonical.model_copy(update={"atom_id": atom_id, "aliases": aliases}))
    return normalized


def _remove_aliases_conflicting_with_declared_names(entities: list[KnowledgeAtomObject]) -> list[KnowledgeAtomObject]:
    declared_name_owners: dict[str, set[int]] = {}
    for index, entity in enumerate(entities):
        for key in _object_keys(entity.name):
            declared_name_owners.setdefault(key, set()).add(index)

    sanitized: list[KnowledgeAtomObject] = []
    for index, entity in enumerate(entities):
        aliases = [
            alias
            for alias in entity.aliases
            if not any(declared_name_owners.get(key, set()) - {index} for key in _object_keys(alias))
        ]
        sanitized.append(entity if aliases == entity.aliases else entity.model_copy(update={"aliases": aliases}))
    return sanitized


def _entity_keys(entity: KnowledgeAtomObject) -> list[str]:
    keys: list[str] = []
    for value in [entity.name, *entity.aliases]:
        keys.extend(_object_keys(value))
    return _dedupe_keys(keys)


def _dedupe_keys(values: Iterable[str]) -> list[str]:
    keys: list[str] = []
    for value in values:
        if value and value not in keys:
            keys.append(value)
    return keys


def _merge_aliases(existing: list[str], values: list[str]) -> list[str]:
    aliases = list(existing)
    seen = {_object_key(value) for value in aliases}
    for value in values:
        text = value.strip()
        key = _object_key(text)
        if text and key not in seen:
            aliases.append(text)
            seen.add(key)
    return aliases


def _preferred_entity(current: KnowledgeAtomObject, candidate: KnowledgeAtomObject) -> KnowledgeAtomObject:
    current_score = _entity_name_score(current.name)
    candidate_score = _entity_name_score(candidate.name)
    if candidate_score > current_score:
        return candidate
    if candidate_score == current_score and len(candidate.name) < len(current.name):
        return candidate
    return current


def _entity_name_score(name: str) -> tuple[int, int, int]:
    text = name.strip()
    generic = text.casefold() in {"this", "it", "project", "system", "document", "本项目", "该项目", "系统", "文档"}
    has_case_signal = any(char.isupper() for char in text[1:])
    has_no_space = " " not in text
    return (
        0 if generic else 1,
        1 if has_case_signal else 0,
        1 if has_no_space else 0,
    )


def _canonical_claim(claim: KnowledgeClaim, alias_map: dict[str, str]) -> KnowledgeClaim:
    names = _unique(alias_map.get(_object_key(name), name) for name in claim.entity_names)
    return claim.model_copy(update={"entity_names": names})


def _canonical_relation(
    relation: KnowledgeRelation,
    alias_map: dict[str, str],
    evidence_by_claim_id: dict[str, list],
) -> KnowledgeRelation:
    subject_name = alias_map.get(_object_key(relation.subject.name), relation.subject.name)
    object_name = alias_map.get(_object_key(relation.object.name), relation.object.name)
    subject = relation.subject.model_copy(update={"name": subject_name})
    obj = relation.object.model_copy(update={"name": object_name})
    evidence = relation.evidence or _dedupe_evidence(
        [
            span
            for claim_id in relation.source_claim_ids
            for span in evidence_by_claim_id.get(claim_id, [])
        ]
    )
    return relation.model_copy(update={"subject": subject, "object": obj, "evidence": evidence})


def _entity_evidence_refs(batch: KnowledgeAtomBatch) -> dict[str, list]:
    refs: dict[str, list] = {}

    def add(name: str, evidence: list) -> None:
        key = _object_key(name)
        if not key:
            return
        bucket = refs.setdefault(key, [])
        seen = {_evidence_key(span) for span in bucket}
        for span in evidence:
            key_tuple = _evidence_key(span)
            if key_tuple not in seen:
                bucket.append(span)
                seen.add(key_tuple)

    for claim in batch.claims:
        for name in claim.entity_names:
            add(name, claim.evidence)
    for relation in batch.relations:
        relation_evidence = relation.evidence or [
            span
            for claim in batch.claims
            if claim.id in relation.source_claim_ids
            for span in claim.evidence
        ]
        add(relation.subject.name, relation_evidence)
        add(relation.object.name, relation_evidence)
    return refs


def _entity_with_inferred_evidence(entity: KnowledgeAtomObject, evidence_by_entity: dict[str, list]) -> KnowledgeAtomObject:
    if entity.evidence:
        return entity
    evidence = evidence_by_entity.get(_object_key(entity.name), [])
    if not evidence:
        return entity
    return entity.model_copy(update={"evidence": evidence})


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
    keys = _object_keys(value)
    return keys[0] if keys else ""


def _object_keys(value: str) -> list[str]:
    text = " ".join(value.casefold().split())
    text = re.sub(r"[\s\-_./:：·]+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff ]+", "", text)
    spaced = " ".join(text.split())
    compact = re.sub(r"\s+", "", spaced)
    return _dedupe_keys([spaced, compact])


def _evidence_key(span: object) -> tuple[str, int | None, str]:
    return (
        getattr(span, "source_record_id", ""),
        getattr(span, "source_unit_index", None),
        getattr(span, "excerpt_hash", None) or getattr(span, "excerpt", ""),
    )


def _dedupe_evidence(values: list) -> list:
    output: list = []
    seen: set[tuple[str, int | None, str]] = set()
    for span in values:
        key = _evidence_key(span)
        if key not in seen:
            output.append(span)
            seen.add(key)
    return output
