from __future__ import annotations

from dataclasses import dataclass

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.knowledge_extract import CompileContext, ContentUnit, KnowledgeExtract
from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.semantic.source_digest import build_source_digest_from_extract


@dataclass(frozen=True)
class SegmentSemanticArtifacts:
    knowledge_extract: KnowledgeExtract
    source_digest: SourceDigest
    knowledge_atom_batch: KnowledgeAtomBatch


@dataclass(frozen=True)
class AggregatedSemanticArtifacts:
    knowledge_extract: KnowledgeExtract
    source_digest: SourceDigest
    knowledge_atom_batch: KnowledgeAtomBatch
    stats: dict[str, int]


def aggregate_segment_semantic_artifacts(
    artifacts: list[SegmentSemanticArtifacts],
) -> AggregatedSemanticArtifacts:
    """Merge segment-level semantic artifacts before source-level page planning."""

    if not artifacts:
        raise ValueError("Cannot aggregate empty segment semantic artifacts.")
    if len(artifacts) == 1:
        item = artifacts[0]
        return AggregatedSemanticArtifacts(
            knowledge_extract=item.knowledge_extract,
            source_digest=item.source_digest,
            knowledge_atom_batch=item.knowledge_atom_batch,
            stats=_aggregation_stats(1, item.knowledge_atom_batch),
        )

    aggregate_extract, unit_index_maps = _aggregate_knowledge_extracts([item.knowledge_extract for item in artifacts])
    aggregate_digest = build_source_digest_from_extract(aggregate_extract)
    aggregate_atoms = _aggregate_atom_batches(
        [item.knowledge_atom_batch for item in artifacts],
        source_digest_id=aggregate_digest.digest_id,
        unit_index_maps=unit_index_maps,
    )
    return AggregatedSemanticArtifacts(
        knowledge_extract=aggregate_extract,
        source_digest=aggregate_digest,
        knowledge_atom_batch=aggregate_atoms,
        stats=_aggregation_stats(len(artifacts), aggregate_atoms),
    )


def _aggregate_knowledge_extracts(
    extracts: list[KnowledgeExtract],
) -> tuple[KnowledgeExtract, list[dict[int, int]]]:
    first = extracts[0]
    content_units: list[ContentUnit] = []
    unit_index_maps: list[dict[int, int]] = []
    primary_blocks: list[str] = []
    links: list[str] = []
    warnings: list[str] = []

    for segment_index, extract in enumerate(extracts):
        index_map: dict[int, int] = {}
        for unit in extract.content_units:
            new_index = len(content_units)
            index_map[unit.index] = new_index
            content_units.append(
                unit.model_copy(
                    update={
                        "index": new_index,
                        "metadata": {
                            **unit.metadata,
                            "segment_index": segment_index,
                            "segment_unit_index": unit.index,
                        },
                    }
                )
            )
        unit_index_maps.append(index_map)
        primary = extract.compile_context.primary_content.strip()
        if primary:
            primary_blocks.append(primary)
        links.extend(item for item in extract.compile_context.links if item not in links)
        warnings.extend(f"segment:{segment_index}:{warning}" for warning in extract.warnings)

    compile_context = CompileContext(
        primary_content="\n\n".join(primary_blocks),
        supporting_evidence=[
            evidence
            for extract in extracts
            for evidence in extract.compile_context.supporting_evidence
        ],
        links=links,
        latest_unit_indexes=[unit.index for unit in content_units],
    )
    return (
        first.model_copy(
            update={
                "content_units": content_units,
                "compile_context": compile_context,
                "confidence": min(extract.confidence for extract in extracts),
                "warnings": _dedupe(warnings),
            }
        ),
        unit_index_maps,
    )


def _aggregate_atom_batches(
    batches: list[KnowledgeAtomBatch],
    *,
    source_digest_id: str,
    unit_index_maps: list[dict[int, int]],
) -> KnowledgeAtomBatch:
    entities: dict[tuple[str, str], KnowledgeAtomObject] = {}
    claims: list[KnowledgeClaim] = []
    claim_id_by_segment_key: dict[tuple[int, str], str] = {}
    claim_id_by_text: dict[str, str] = {}
    used_claim_ids: set[str] = set()
    evidence: dict[tuple[str, int | None, str], KnowledgeEvidenceSpan] = {}
    warnings: list[str] = []

    for segment_index, batch in enumerate(batches):
        unit_index_map = unit_index_maps[segment_index] if segment_index < len(unit_index_maps) else {}
        for entity in batch.entities:
            entities.setdefault((entity.object_type, entity.name.casefold()), entity)
        for claim in batch.claims:
            normalized_claim = _normalize_text(claim.claim)
            mapped_id = claim_id_by_text.get(normalized_claim)
            rewritten_evidence = [
                _rewrite_evidence_span(span, source_digest_id=source_digest_id, unit_index_map=unit_index_map)
                for span in claim.evidence
            ]
            if mapped_id:
                claim_id_by_segment_key[(segment_index, claim.id)] = mapped_id
                _merge_claim_evidence(claims, mapped_id, rewritten_evidence)
                for span in rewritten_evidence:
                    evidence[_evidence_key(span)] = span
                continue

            mapped_id = _unique_atom_id(claim.id, used_claim_ids, segment_index=segment_index)
            used_claim_ids.add(mapped_id)
            claim_id_by_text[normalized_claim] = mapped_id
            claim_id_by_segment_key[(segment_index, claim.id)] = mapped_id
            for span in rewritten_evidence:
                evidence[_evidence_key(span)] = span
            claims.append(
                claim.model_copy(
                    update={
                        "id": mapped_id,
                        "evidence": rewritten_evidence,
                    }
                )
            )

    relations: list[KnowledgeRelation] = []
    relation_keys: set[tuple[str, str, str, tuple[str, ...]]] = set()
    used_relation_ids: set[str] = set()
    for segment_index, batch in enumerate(batches):
        unit_index_map = unit_index_maps[segment_index] if segment_index < len(unit_index_maps) else {}
        for relation in batch.relations:
            mapped_claim_ids = [
                claim_id_by_segment_key.get((segment_index, claim_id), claim_id)
                for claim_id in relation.source_claim_ids
            ]
            key = (
                relation.subject.name.casefold(),
                relation.predicate,
                relation.object.name.casefold(),
                tuple(mapped_claim_ids),
            )
            if key in relation_keys:
                continue
            relation_keys.add(key)
            mapped_relation_id = _unique_atom_id(relation.id, used_relation_ids, segment_index=segment_index)
            used_relation_ids.add(mapped_relation_id)
            rewritten_evidence = [
                _rewrite_evidence_span(span, source_digest_id=source_digest_id, unit_index_map=unit_index_map)
                for span in relation.evidence
            ]
            for span in rewritten_evidence:
                evidence[_evidence_key(span)] = span
            relations.append(
                relation.model_copy(
                    update={
                        "id": mapped_relation_id,
                        "source_claim_ids": mapped_claim_ids,
                        "evidence": rewritten_evidence,
                    }
                )
            )
            entities.setdefault((relation.subject.object_type, relation.subject.name.casefold()), relation.subject)
            entities.setdefault((relation.object.object_type, relation.object.name.casefold()), relation.object)
        warnings.extend(f"segment:{segment_index}:{warning}" for warning in batch.warnings)

    return KnowledgeAtomBatch(
        source_digest_id=source_digest_id,
        entities=list(entities.values()),
        claims=claims,
        relations=relations,
        evidence=list(evidence.values()),
        warnings=_dedupe(warnings),
    )


def _merge_claim_evidence(
    claims: list[KnowledgeClaim],
    claim_id: str,
    incoming: list[KnowledgeEvidenceSpan],
) -> None:
    for index, claim in enumerate(claims):
        if claim.id != claim_id:
            continue
        existing = {_evidence_key(span): span for span in claim.evidence}
        for span in incoming:
            existing.setdefault(_evidence_key(span), span)
        claims[index] = claim.model_copy(update={"evidence": list(existing.values())})
        return


def _rewrite_evidence_span(
    span: KnowledgeEvidenceSpan,
    *,
    source_digest_id: str,
    unit_index_map: dict[int, int],
) -> KnowledgeEvidenceSpan:
    source_unit_index = span.source_unit_index
    if source_unit_index is not None:
        source_unit_index = unit_index_map.get(source_unit_index, source_unit_index)
    return span.model_copy(
        update={
            "source_digest_id": source_digest_id,
            "source_unit_index": source_unit_index,
        }
    )


def _unique_atom_id(atom_id: str, used: set[str], *, segment_index: int) -> str:
    if atom_id not in used:
        return atom_id
    candidate = f"s{segment_index}_{atom_id}"
    suffix = 2
    while candidate in used:
        candidate = f"s{segment_index}_{atom_id}_{suffix}"
        suffix += 1
    return candidate


def _aggregation_stats(segment_count: int, batch: KnowledgeAtomBatch) -> dict[str, int]:
    summary = batch.summary()
    return {
        "segment_count": segment_count,
        "entities": summary["entities"],
        "claims": summary["claims"],
        "relations": summary["relations"],
        "evidence_spans": summary["evidence_spans"],
    }


def _evidence_key(span: KnowledgeEvidenceSpan) -> tuple[str, int | None, str]:
    return (span.source_digest_id, span.source_unit_index, span.excerpt_hash or span.excerpt)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
