from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan


@dataclass(frozen=True)
class KnowledgeAtomClosureIssue:
    code: str
    message: str
    atom_id: str | None = None


@dataclass(frozen=True)
class KnowledgeAtomClosure:
    source_digest_id: str
    claim_ids: list[str] = field(default_factory=list)
    relation_ids: list[str] = field(default_factory=list)
    entity_names: list[str] = field(default_factory=list)
    evidence_keys: list[tuple[str, int | None, str]] = field(default_factory=list)
    source_digest_ids: list[str] = field(default_factory=list)
    issues: list[KnowledgeAtomClosureIssue] = field(default_factory=list)

    @property
    def atom_ids(self) -> list[str]:
        return _dedupe([*self.claim_ids, *self.relation_ids])


def close_operation_atoms(
    batch: KnowledgeAtomBatch,
    operation: WikiPageOperation,
) -> KnowledgeAtomClosure:
    """Derive the deterministic atom closure for one page-plan operation.

    The page plan chooses claims as the spine. The closure then carries the
    supported relations, entities, evidence spans, and source digest ids needed
    to render or validate that page without asking another model to infer them.
    """

    claims_by_id = {claim.id: claim for claim in batch.claims}
    relations_by_id = {relation.id: relation for relation in batch.relations}
    selected_claim_ids = _dedupe(operation.selected_claim_ids)
    explicit_relation_ids = _dedupe(operation.selected_relation_ids)
    issues: list[KnowledgeAtomClosureIssue] = []

    for claim_id in selected_claim_ids:
        if claim_id not in claims_by_id:
            issues.append(
                KnowledgeAtomClosureIssue(
                    code="unknown_selected_claim",
                    atom_id=claim_id,
                    message=f"Selected claim atom does not exist: {claim_id}.",
                )
            )

    selected_relation_ids: list[str] = []
    for relation in batch.relations:
        if _relation_supported_by_claims(relation, selected_claim_ids):
            selected_relation_ids.append(relation.id)

    for relation_id in explicit_relation_ids:
        relation = relations_by_id.get(relation_id)
        if relation is None:
            issues.append(
                KnowledgeAtomClosureIssue(
                    code="unknown_selected_relation",
                    atom_id=relation_id,
                    message=f"Selected relation atom does not exist: {relation_id}.",
                )
            )
            continue
        selected_relation_ids.append(relation_id)
        missing_claims = sorted(set(relation.source_claim_ids).difference(selected_claim_ids))
        if missing_claims:
            issues.append(
                KnowledgeAtomClosureIssue(
                    code="relation_selected_without_source_claim",
                    atom_id=relation_id,
                    message=(
                        f"Selected relation atom {relation_id} references claim atom ids "
                        f"not selected by the same operation: {', '.join(missing_claims)}."
                    ),
                )
            )

    selected_claims = [claims_by_id[claim_id] for claim_id in selected_claim_ids if claim_id in claims_by_id]
    selected_relations = [relations_by_id[relation_id] for relation_id in _dedupe(selected_relation_ids) if relation_id in relations_by_id]
    entity_names = _closed_entity_names(selected_claims, selected_relations, batch.entities)
    evidence_spans = _closed_evidence_spans(batch, selected_claims, selected_relations)
    source_digest_ids = _dedupe(operation.source_digest_ids)
    if not source_digest_ids:
        source_digest_ids = _dedupe(
            [
                batch.source_digest_id,
                *(span.source_digest_id for span in evidence_spans),
            ]
        )

    return KnowledgeAtomClosure(
        source_digest_id=batch.source_digest_id,
        claim_ids=[claim.id for claim in selected_claims],
        relation_ids=[relation.id for relation in selected_relations],
        entity_names=entity_names,
        evidence_keys=[_evidence_key(span) for span in evidence_spans],
        source_digest_ids=source_digest_ids,
        issues=issues,
    )


def close_plan_atoms(
    batch: KnowledgeAtomBatch | None,
    page_plan: WikiPagePlan,
) -> KnowledgeAtomBatch | None:
    """Return the selected atom batch needed by the compile/review agents."""

    if batch is None:
        return None
    closures = [
        close_operation_atoms(batch, operation)
        for operation in page_plan.operations
        if operation.action != "skip"
    ]
    claim_ids = _dedupe(claim_id for closure in closures for claim_id in closure.claim_ids)
    relation_ids = _dedupe(relation_id for closure in closures for relation_id in closure.relation_ids)
    entity_names = {name.casefold() for closure in closures for name in closure.entity_names}

    selected_claims = [claim for claim in batch.claims if claim.id in claim_ids]
    selected_relations = [relation for relation in batch.relations if relation.id in relation_ids]
    selected_entities = [
        entity
        for entity in batch.entities
        if entity.name.casefold() in entity_names
        or (entity.atom_id and entity.atom_id in set(claim_ids) | set(relation_ids))
    ]
    selected_evidence = _closed_evidence_spans(batch, selected_claims, selected_relations)
    return KnowledgeAtomBatch(
        source_digest_id=batch.source_digest_id,
        entities=selected_entities,
        claims=selected_claims,
        relations=selected_relations,
        evidence=selected_evidence,
        warnings=list(batch.warnings),
    )


def _relation_supported_by_claims(relation: KnowledgeRelation, selected_claim_ids: list[str]) -> bool:
    if not relation.source_claim_ids:
        return False
    return set(relation.source_claim_ids).issubset(set(selected_claim_ids))


def _closed_entity_names(
    claims: list[KnowledgeClaim],
    relations: list[KnowledgeRelation],
    entities: list[KnowledgeAtomObject],
) -> list[str]:
    names = _dedupe(
        [
            *(entity_name for claim in claims for entity_name in claim.entity_names),
            *(relation.subject.name for relation in relations),
            *(relation.object.name for relation in relations),
        ]
    )
    known = {entity.name.casefold(): entity.name for entity in entities}
    return _dedupe(known.get(name.casefold(), name) for name in names)


def _closed_evidence_spans(
    batch: KnowledgeAtomBatch,
    claims: list[KnowledgeClaim],
    relations: list[KnowledgeRelation],
) -> list[KnowledgeEvidenceSpan]:
    top_level_evidence_by_key = {_evidence_key(span): span for span in batch.evidence}
    evidence_by_key: dict[tuple[str, int | None, str], KnowledgeEvidenceSpan] = {}

    def add_selected_span(span: KnowledgeEvidenceSpan) -> None:
        key = _evidence_key(span)
        evidence_by_key.setdefault(key, top_level_evidence_by_key.get(key, span))

    for claim in claims:
        for span in claim.evidence:
            add_selected_span(span)
    for relation in relations:
        for span in relation.evidence:
            add_selected_span(span)
    return list(evidence_by_key.values())


def _evidence_key(span: KnowledgeEvidenceSpan) -> tuple[str, int | None, str]:
    return (span.source_digest_id, span.source_unit_index, span.excerpt_hash or span.excerpt)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
