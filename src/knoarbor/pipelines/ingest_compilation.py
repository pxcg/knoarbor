from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from knoarbor.core.errors import InternalKnoArborError
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.semantic.knowledge_atom_normalization import normalize_knowledge_atom_batch


class IngestCompilationIntegrityError(InternalKnoArborError):
    """Deterministic compiler output violated an internal postcondition."""


@dataclass(frozen=True)
class IndexExtractResult:
    knowledge_atom_batch: KnowledgeAtomBatch
    synthesis_topics: list[str]
    ambiguities: list[dict[str, object]]
    semantic_metrics: dict[str, object]
    compilation_diagnostics: dict[str, object] = field(default_factory=dict)
    segment_semantic_metrics: tuple[dict[str, object], ...] = ()

    @property
    def synthesis(self) -> str:
        return render_synthesis_topics(self.synthesis_topics)


def merge_segment_extracts(extracts: list[IndexExtractResult], source_record_id: str) -> IndexExtractResult:
    entities_by_key: dict[str, Any] = {}
    claims_by_id: dict[str, Any] = {}
    relations_by_id: dict[str, Any] = {}
    for extract in extracts:
        _merge_entities(entities_by_key, extract.knowledge_atom_batch.entities)
        _merge_claims(claims_by_id, extract.knowledge_atom_batch.claims)
        _merge_relations(relations_by_id, extract.knowledge_atom_batch.relations)

    synthesis_topics = dedupe_texts([topic for extract in extracts for topic in extract.synthesis_topics])
    atom_batch = KnowledgeAtomBatch(
        source_record_id=source_record_id,
        entities=_unique_objects(entities_by_key.values()),
        claims=list(claims_by_id.values()),
        relations=list(relations_by_id.values()),
        synthesis=render_synthesis_topics(synthesis_topics),
    )
    return IndexExtractResult(
        knowledge_atom_batch=normalize_knowledge_atom_batch(atom_batch),
        synthesis_topics=synthesis_topics,
        ambiguities=_dedupe_ambiguities([item for extract in extracts for item in extract.ambiguities]),
        semantic_metrics=merge_semantic_metrics([extract.semantic_metrics for extract in extracts]),
        compilation_diagnostics=_merge_compilation_diagnostics(extracts),
        segment_semantic_metrics=tuple(
            metric
            for extract in extracts
            for metric in (extract.segment_semantic_metrics or (extract.semantic_metrics,))
        ),
    )


def validate_compiled_index_metadata(compiled: IndexExtractResult, *, source_record_id: str) -> None:
    """Enforce compiler-owned postconditions once, after deterministic merge."""

    batch = compiled.knowledge_atom_batch
    errors: list[str] = []
    if batch.source_record_id != source_record_id:
        errors.append(
            f"atom batch source_record_id {batch.source_record_id!r} does not match {source_record_id!r}"
        )

    atom_ids = [*(claim.id for claim in batch.claims), *(relation.id for relation in batch.relations)]
    duplicate_ids = sorted({atom_id for atom_id in atom_ids if atom_ids.count(atom_id) > 1})
    if duplicate_ids:
        errors.append(f"duplicate atom ids: {', '.join(duplicate_ids)}")

    declared_entities = {_name_key(entity.name) for entity in batch.entities}
    claims_by_id = {claim.id: claim for claim in batch.claims}
    for entity in batch.entities:
        if not entity.evidence:
            errors.append(f"entity {entity.name!r} has no evidence")
        elif _has_foreign_evidence(entity.evidence, source_record_id):
            errors.append(f"entity {entity.name!r} has foreign evidence")
    for claim in batch.claims:
        if _has_foreign_evidence(claim.evidence, source_record_id):
            errors.append(f"claim {claim.id!r} has foreign evidence")
        missing_entities = sorted(name for name in claim.entity_names if _name_key(name) not in declared_entities)
        if missing_entities:
            errors.append(f"claim {claim.id!r} references undeclared entities: {', '.join(missing_entities)}")
    for relation in batch.relations:
        missing_claims = sorted(claim_id for claim_id in relation.source_claim_ids if claim_id not in claims_by_id)
        if missing_claims:
            errors.append(f"relation {relation.id!r} references missing claims: {', '.join(missing_claims)}")
        if not relation.evidence:
            errors.append(f"relation {relation.id!r} has no evidence")
        elif _has_foreign_evidence(relation.evidence, source_record_id):
            errors.append(f"relation {relation.id!r} has foreign evidence")
        missing_endpoints = sorted(
            endpoint.name
            for endpoint in (relation.subject, relation.object)
            if _name_key(endpoint.name) not in declared_entities
        )
        if missing_endpoints:
            errors.append(f"relation {relation.id!r} references undeclared entities: {', '.join(missing_endpoints)}")
    if errors:
        raise IngestCompilationIntegrityError(
            "Compiled index metadata failed deterministic integrity validation: " + "; ".join(errors)
        )


def _has_foreign_evidence(evidence: list[Any], source_record_id: str) -> bool:
    return any(span.source_record_id != source_record_id for span in evidence)


def _merge_entities(target: dict[str, Any], entities: list[Any]) -> None:
    for entity in entities:
        keys = [_name_key(entity.name), *(_name_key(alias) for alias in entity.aliases)]
        existing_key = next((key for key in keys if key in target), keys[0])
        existing = target.get(existing_key)
        merged = (
            entity
            if existing is None
            else existing.model_copy(
                update={
                    "aliases": dedupe_texts([*existing.aliases, entity.name, *entity.aliases]),
                    "evidence": _merge_evidence(existing.evidence, entity.evidence),
                }
            )
        )
        if existing is not None:
            for key, value in list(target.items()):
                if value is existing:
                    target[key] = merged
        for key in keys:
            target[key] = merged


def _merge_claims(target: dict[str, Any], claims: list[Any]) -> None:
    for claim in claims:
        existing = target.get(claim.id)
        target[claim.id] = (
            claim
            if existing is None
            else existing.model_copy(
                update={
                    "evidence": _merge_evidence(existing.evidence, claim.evidence),
                    "entity_names": dedupe_texts([*existing.entity_names, *claim.entity_names]),
                    "entity_ids": dedupe_texts([*existing.entity_ids, *claim.entity_ids]),
                }
            )
        )


def _merge_relations(target: dict[str, Any], relations: list[Any]) -> None:
    for relation in relations:
        existing = target.get(relation.id)
        target[relation.id] = (
            relation
            if existing is None
            else existing.model_copy(
                update={
                    "source_claim_ids": dedupe_texts([*existing.source_claim_ids, *relation.source_claim_ids]),
                    "evidence": _merge_evidence(existing.evidence, relation.evidence),
                }
            )
        )


def _name_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _unique_objects(values: Any) -> list[Any]:
    output: list[Any] = []
    seen: set[int] = set()
    for value in values:
        identity = id(value)
        if identity not in seen:
            seen.add(identity)
            output.append(value)
    return output


def _merge_evidence(left: list[Any], right: list[Any]) -> list[Any]:
    output: list[Any] = []
    seen: set[tuple[object, ...]] = set()
    for span in [*left, *right]:
        key = (span.source_record_id, span.source_unit_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
        if key not in seen:
            seen.add(key)
            output.append(span)
    return output


def _merge_compilation_diagnostics(extracts: list[IndexExtractResult]) -> dict[str, object]:
    candidates: dict[str, int] = {}
    accepted: dict[str, int] = {}
    rejected: dict[str, list[dict[str, object]]] = {
        "rejected_aliases": [],
        "rejected_entities": [],
        "rejected_ambiguities": [],
        "rejected_claims": [],
        "rejected_claim_entity_references": [],
        "rejected_relations": [],
    }
    for segment_index, extract in enumerate(extracts):
        diagnostics = extract.compilation_diagnostics
        for target, key in ((candidates, "candidates"), (accepted, "accepted")):
            values = diagnostics.get(key)
            if isinstance(values, dict):
                for name, value in values.items():
                    if isinstance(value, int):
                        target[str(name)] = target.get(str(name), 0) + value
        for key, target in rejected.items():
            values = diagnostics.get(key)
            if isinstance(values, list):
                target.extend({"segment_index": segment_index, **item} for item in values if isinstance(item, dict))
    return {"candidates": candidates, "accepted": accepted, **rejected}


def merge_semantic_metrics(items: list[dict[str, object]]) -> dict[str, object]:
    merged = _empty_semantic_metrics()
    calls: list[object] = []
    by_contract: list[object] = []
    for metrics in items:
        for key in (
            "semantic_call_count",
            "prompt_tokens",
            "prompt_cached_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
            "prompt_stable_chars",
            "prompt_dynamic_chars",
            "completion_tokens",
            "total_tokens",
        ):
            merged[key] = int(merged.get(key) or 0) + int(metrics.get(key) or 0)
        merged["elapsed_seconds"] = float(merged.get("elapsed_seconds") or 0.0) + float(metrics.get("elapsed_seconds") or 0.0)
        calls.extend(metrics.get("calls") if isinstance(metrics.get("calls"), list) else [])
        by_contract.extend(metrics.get("by_contract") if isinstance(metrics.get("by_contract"), list) else [])
    total_tokens = int(merged["total_tokens"] or 0)
    elapsed = float(merged["elapsed_seconds"] or 0.0)
    prompt_tokens = int(merged["prompt_tokens"] or 0)
    cached_tokens = int(merged["prompt_cached_tokens"] or 0)
    stable_chars = int(merged["prompt_stable_chars"] or 0)
    dynamic_chars = int(merged["prompt_dynamic_chars"] or 0)
    merged.update(
        {
            "calls": calls,
            "by_contract": by_contract,
            "tokens_per_second": (total_tokens / elapsed) if elapsed > 0 else None,
            "prompt_cache_rate": (cached_tokens / prompt_tokens) if prompt_tokens > 0 else None,
            "dynamic_to_stable_ratio": (dynamic_chars / stable_chars) if stable_chars > 0 else None,
        }
    )
    return merged


def dedupe_texts(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def render_synthesis_topics(topics: list[str]) -> str:
    if len(topics) <= 1:
        return topics[0] if topics else ""
    return "\n".join(f"- {topic}" for topic in topics)


def _dedupe_ambiguities(values: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    seen: set[tuple[str, str, tuple[int, ...]]] = set()
    for value in values:
        positions = value.get("unit_positions")
        key = (
            str(value.get("kind") or "").strip().casefold(),
            str(value.get("description") or "").strip(),
            tuple(int(item) for item in positions if isinstance(item, int)) if isinstance(positions, list) else (),
        )
        if key[0] and key[1] and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _empty_semantic_metrics() -> dict[str, object]:
    return {
        "semantic_call_count": 0,
        "prompt_tokens": 0,
        "prompt_cached_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "prompt_stable_chars": 0,
        "prompt_dynamic_chars": 0,
        "dynamic_to_stable_ratio": None,
        "completion_tokens": 0,
        "total_tokens": 0,
        "elapsed_seconds": 0.0,
        "tokens_per_second": None,
        "prompt_cache_rate": None,
        "by_contract": [],
        "calls": [],
    }
