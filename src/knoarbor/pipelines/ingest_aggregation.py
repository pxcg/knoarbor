from __future__ import annotations

from dataclasses import dataclass

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeAtomQualityReport,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.knowledge_extract import CompileContext, ContentUnit, KnowledgeExtract
from knoarbor.core.schemas.source_digest import SourceDigest, SourceDigestContribution, SourceDigestUnresolvedItem
from knoarbor.semantic.knowledge_atom_quality import evaluate_knowledge_atoms
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
    knowledge_atom_quality: KnowledgeAtomQualityReport
    stats: dict[str, int]


def aggregate_segment_semantic_artifacts(
    artifacts: list[SegmentSemanticArtifacts],
) -> AggregatedSemanticArtifacts:
    """Merge segment-level semantic artifacts before source-level page planning."""

    if not artifacts:
        raise ValueError("Cannot aggregate empty segment semantic artifacts.")
    if len(artifacts) == 1:
        item = artifacts[0]
        atom_quality = evaluate_knowledge_atoms(item.knowledge_atom_batch)
        source_digest = _enrich_source_digest_with_atom_audit(
            item.source_digest,
            item.knowledge_atom_batch,
            atom_quality,
        )
        return AggregatedSemanticArtifacts(
            knowledge_extract=item.knowledge_extract,
            source_digest=source_digest,
            knowledge_atom_batch=item.knowledge_atom_batch,
            knowledge_atom_quality=atom_quality,
            stats=_aggregation_stats(1, item.knowledge_atom_batch, atom_quality),
        )

    aggregate_extract, unit_index_maps = _aggregate_knowledge_extracts([item.knowledge_extract for item in artifacts])
    aggregate_digest = build_source_digest_from_extract(aggregate_extract)
    aggregate_atoms = _aggregate_atom_batches(
        [item.knowledge_atom_batch for item in artifacts],
        source_digest_id=aggregate_digest.digest_id,
        unit_index_maps=unit_index_maps,
    )
    aggregate_quality = evaluate_knowledge_atoms(aggregate_atoms)
    aggregate_digest = _enrich_source_digest_with_atom_audit(
        aggregate_digest,
        aggregate_atoms,
        aggregate_quality,
    )
    return AggregatedSemanticArtifacts(
        knowledge_extract=aggregate_extract,
        source_digest=aggregate_digest,
        knowledge_atom_batch=aggregate_atoms,
        knowledge_atom_quality=aggregate_quality,
        stats=_aggregation_stats(len(artifacts), aggregate_atoms, aggregate_quality),
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


def _enrich_source_digest_with_atom_audit(
    digest: SourceDigest,
    batch: KnowledgeAtomBatch,
    quality: KnowledgeAtomQualityReport,
) -> SourceDigest:
    return digest.model_copy(
        update={
            "contribution_map": _claim_contributions(batch),
            "unresolved_items": [
                *digest.unresolved_items,
                *_quality_unresolved_items(quality),
            ],
        }
    )


def _claim_contributions(batch: KnowledgeAtomBatch) -> list[SourceDigestContribution]:
    contributions: list[SourceDigestContribution] = []
    for claim in batch.claims:
        unit_ids = _evidence_unit_ids(claim.evidence)
        contributions.append(
            SourceDigestContribution(
                item_id=claim.id,
                contribution=claim.claim,
                evidence_unit_ids=unit_ids,
                status="pending",
            )
        )
    return contributions


def _quality_unresolved_items(quality: KnowledgeAtomQualityReport) -> list[SourceDigestUnresolvedItem]:
    items: list[SourceDigestUnresolvedItem] = []
    actionable_issues = [issue for issue in quality.issues if issue.severity != "info"]
    for index, issue in enumerate(actionable_issues, start=1):
        items.append(
            SourceDigestUnresolvedItem(
                item_id=f"Q{index}",
                item_type="unresolved" if issue.severity != "error" else "rejected",
                reason=f"{issue.issue_type}: {issue.message}",
                evidence_unit_ids=[],
            )
        )
    return items


def _evidence_unit_ids(evidence: list[KnowledgeEvidenceSpan]) -> list[str]:
    ids: list[str] = []
    for span in evidence:
        if span.source_unit_index is None:
            continue
        unit_id = f"U{span.source_unit_index + 1}"
        if unit_id not in ids:
            ids.append(unit_id)
    return ids


def _aggregation_stats(segment_count: int, batch: KnowledgeAtomBatch, quality: KnowledgeAtomQualityReport) -> dict[str, int]:
    summary = batch.summary()
    quality_summary = quality.summary()
    return {
        "segment_count": segment_count,
        "entities": summary["entities"],
        "claims": summary["claims"],
        "relations": summary["relations"],
        "evidence_spans": summary["evidence_spans"],
        "atom_quality_unsupported": quality_summary["unsupported"],
        "atom_quality_conflicting": quality_summary["conflicting"],
        "atom_quality_rejected": quality_summary["rejected"],
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
