from __future__ import annotations

from hashlib import sha1
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeAtomObject
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore


ENTITY_REGISTRY_SCHEMA = "entity_registry.v2"


class EntityContribution(BaseModel):
    raw_record_id: str
    source_record_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)


class EntityRegistryEntry(BaseModel):
    entity_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    contributions: list[EntityContribution] = Field(default_factory=list)


class EntityRegistry(BaseModel):
    schema_version: str = ENTITY_REGISTRY_SCHEMA
    entries: list[EntityRegistryEntry] = Field(default_factory=list)


@dataclass(frozen=True)
class EntityIdentityResolution:
    atom_batch: KnowledgeAtomBatch
    registry: EntityRegistry


def prepare_entity_identity_resolution(
    vault_path: Path,
    batch: KnowledgeAtomBatch,
    *,
    raw_record_id: str,
) -> EntityIdentityResolution:
    """Bind one source-local atom batch to vault-global entity identities.

    This is deliberately the only cross-source operation in ingest. It uses
    observed explicit names and aliases, never semantic similarity.
    """

    registry = _remove_raw_contributions(read_entity_registry(vault_path), raw_record_id)
    resolved, registry = _resolve_batch(registry, batch, raw_record_id=raw_record_id)
    return EntityIdentityResolution(
        atom_batch=resolved,
        registry=registry,
    )


def read_entity_registry(vault_path: Path) -> EntityRegistry:
    """Build the entity projection from active source-revision contributions."""

    store_path = vault_path.expanduser().resolve() / ".knoarbor" / "ingest.sqlite"
    if not store_path.exists():
        return EntityRegistry()
    registry = EntityRegistry()
    for payload in TransactionalIngestStore(vault_path).active_entity_contributions():
        name = str(payload.get("name") or "").strip()
        raw_record_id = str(payload.get("raw_record_id") or "")
        if not name or not raw_record_id:
            continue
        source_record_id = str(payload.get("source_record_id") or "")
        entity_id = str(payload.get("entity_id") or _entity_id(raw_record_id, name))
        aliases = [str(value) for value in payload.get("aliases", []) if isinstance(value, str)]
        entry = next((item for item in registry.entries if item.entity_id == entity_id), None)
        if entry is None:
            entry = EntityRegistryEntry(entity_id=entity_id, canonical_name=name)
            registry.entries.append(entry)
        _add_contribution(
            entry, EntityContribution(raw_record_id=raw_record_id, source_record_id=source_record_id, name=name, aliases=aliases)
        )
    return registry


def _resolve_batch(registry: EntityRegistry, batch: KnowledgeAtomBatch, *, raw_record_id: str) -> tuple[KnowledgeAtomBatch, EntityRegistry]:
    by_key = _entries_by_key(registry)
    resolved_entities: list[KnowledgeAtomObject] = []
    name_map: dict[str, EntityRegistryEntry] = {}

    for entity in batch.entities:
        contribution = EntityContribution(
            raw_record_id=raw_record_id,
            source_record_id=batch.source_record_id,
            name=entity.name,
            aliases=entity.aliases,
        )
        entry = _match_entry(contribution, registry.entries, by_key)
        if entry is None:
            entry = EntityRegistryEntry(
                entity_id=_entity_id(raw_record_id, entity.name),
                canonical_name=entity.name,
                aliases=_unique([*entity.aliases]),
                contributions=[],
            )
            registry.entries.append(entry)
        _add_contribution(entry, contribution)
        for value in [entity.name, *entity.aliases]:
            key = entity_key(value)
            if key:
                name_map[key] = entry
        resolved_entities.append(entity.model_copy(update={"atom_id": entry.entity_id}))
        by_key = _entries_by_key(registry)

    resolved_relations = []
    for relation in batch.relations:
        subject = _resolved_endpoint(relation.subject, name_map)
        obj = _resolved_endpoint(relation.object, name_map)
        resolved_relations.append(relation.model_copy(update={"subject": subject, "object": obj}))

    resolved_claims = []
    for claim in batch.claims:
        entity_ids = _unique_ids(entry.entity_id for name in claim.entity_names if (entry := name_map.get(entity_key(name))) is not None)
        resolved_claims.append(claim.model_copy(update={"entity_ids": entity_ids}))

    return batch.model_copy(
        update={
            "entities": _unique_entities(resolved_entities),
            "claims": resolved_claims,
            "relations": resolved_relations,
        }
    ), registry


def _match_entry(
    contribution: EntityContribution,
    entries: list[EntityRegistryEntry],
    by_key: dict[str, list[EntityRegistryEntry]],
) -> EntityRegistryEntry | None:
    for value in [contribution.name, *contribution.aliases]:
        matches = by_key.get(entity_key(value), [])
        if len(matches) == 1:
            return matches[0]
    acronym = _acronym_key(contribution.name)
    if acronym:
        matches = [entry for entry in entries if acronym in _entry_acronyms(entry)]
        if len(matches) == 1:
            return matches[0]
    return None


def _resolved_endpoint(endpoint: KnowledgeAtomObject, name_map: dict[str, EntityRegistryEntry]) -> KnowledgeAtomObject:
    entry = name_map.get(entity_key(endpoint.name))
    if entry is None:
        return endpoint
    return endpoint.model_copy(update={"atom_id": entry.entity_id})


def _unique_entities(entities: list[KnowledgeAtomObject]) -> list[KnowledgeAtomObject]:
    output: list[KnowledgeAtomObject] = []
    seen: set[str] = set()
    for entity in entities:
        key = entity.atom_id or entity_key(entity.name)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(entity)
    return output


def _add_contribution(entry: EntityRegistryEntry, contribution: EntityContribution) -> None:
    entry.contributions = [item for item in entry.contributions if item.raw_record_id != contribution.raw_record_id]
    entry.contributions.append(contribution)
    _refresh_entry_labels(entry)


def _remove_raw_contributions(registry: EntityRegistry, raw_record_id: str) -> EntityRegistry:
    retained: list[EntityRegistryEntry] = []
    for entry in registry.entries:
        contributions = [item for item in entry.contributions if item.raw_record_id != raw_record_id]
        if not contributions:
            continue
        refreshed = entry.model_copy(update={"contributions": contributions})
        _refresh_entry_labels(refreshed)
        retained.append(refreshed)
    return EntityRegistry(entries=retained)


def _entries_by_key(registry: EntityRegistry) -> dict[str, list[EntityRegistryEntry]]:
    values: dict[str, list[EntityRegistryEntry]] = {}
    for entry in registry.entries:
        for value in [entry.canonical_name, *entry.aliases]:
            key = entity_key(value)
            if key:
                values.setdefault(key, []).append(entry)
    return values


def _refresh_entry_labels(entry: EntityRegistryEntry) -> None:
    names = _unique([item.name for item in entry.contributions])
    if names:
        entry.canonical_name = min(names, key=_registry_label_order)
    aliases = _unique([value for item in entry.contributions for value in [item.name, *item.aliases]])
    entry.aliases = [value for value in aliases if entity_key(value) != entity_key(entry.canonical_name)]


def _registry_label_order(value: str) -> tuple[int, int, str]:
    text = value.strip()
    acronym = bool(re.fullmatch(r"[A-Z0-9]{2,12}", text))
    words = len(re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]+", text))
    return (1 if acronym else 0, -words, entity_key(text))


def entity_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def _entity_id(raw_record_id: str, name: str) -> str:
    seed = f"{raw_record_id}\0{entity_key(name)}"
    return "ent:" + sha1(seed.encode("utf-8")).hexdigest()[:16]


def _acronym_key(value: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{2,12}", text):
        return ""
    return text.upper()


def _entry_acronyms(entry: EntityRegistryEntry) -> set[str]:
    values = [entry.canonical_name, *entry.aliases]
    acronyms: set[str] = set()
    for value in values:
        direct = _acronym_key(value)
        if direct:
            acronyms.add(direct)
            continue
        words = re.findall(r"[A-Za-z0-9]+", value)
        if len(words) >= 2:
            initials = "".join(word[0] for word in words).upper()
            if len(initials) >= 2:
                acronyms.add(initials)
        repeated_to = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9]*)\s*-\s*to\s*-\s*([A-Za-z][A-Za-z0-9]*)\s*", value, flags=re.IGNORECASE)
        if repeated_to and repeated_to.group(1).casefold() == repeated_to.group(2).casefold():
            acronyms.add(f"{repeated_to.group(1)[0]}2{repeated_to.group(2)[0]}".upper())
    return acronyms


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = entity_key(text)
        if text and key and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _unique_ids(values: object) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))
