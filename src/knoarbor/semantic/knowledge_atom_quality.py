from __future__ import annotations

from collections import defaultdict

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomQualityIssue,
    KnowledgeAtomQualityReport,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)


def evaluate_knowledge_atoms(batch: KnowledgeAtomBatch) -> KnowledgeAtomQualityReport:
    """Validate source-local atom consistency before atoms influence page planning."""
    issues: list[KnowledgeAtomQualityIssue] = []
    issues.extend(_duplicate_id_issues(batch))
    issues.extend(_unsupported_claim_issues(batch))
    issues.extend(_unsupported_relation_issues(batch))
    issues.extend(_conflicting_relation_issues(batch.relations))
    issues.extend(_undefined_entity_reference_issues(batch))
    issues.extend(_unused_entity_issues(batch))
    return KnowledgeAtomQualityReport(
        source_digest_id=batch.source_digest_id,
        extracted=batch.summary(),
        issues=issues,
    )


def _duplicate_id_issues(batch: KnowledgeAtomBatch) -> list[KnowledgeAtomQualityIssue]:
    issues: list[KnowledgeAtomQualityIssue] = []
    seen: set[str] = set()
    for atom_id in [*(claim.id for claim in batch.claims), *(relation.id for relation in batch.relations)]:
        if atom_id in seen:
            issues.append(
                KnowledgeAtomQualityIssue(
                    issue_type="duplicate_atom_id",
                    severity="error",
                    atom_id=atom_id,
                    message=f"Duplicate atom id `{atom_id}`.",
                )
            )
        seen.add(atom_id)
    return issues


def _unsupported_claim_issues(batch: KnowledgeAtomBatch) -> list[KnowledgeAtomQualityIssue]:
    issues: list[KnowledgeAtomQualityIssue] = []
    for claim in batch.claims:
        if _has_foreign_evidence(batch.source_digest_id, claim.evidence):
            issues.append(
                KnowledgeAtomQualityIssue(
                    issue_type="unsupported_claim",
                    severity="error",
                    atom_id=claim.id,
                    message="Claim evidence points to a different source digest.",
                )
            )
    return issues


def _unsupported_relation_issues(batch: KnowledgeAtomBatch) -> list[KnowledgeAtomQualityIssue]:
    claim_ids = {claim.id for claim in batch.claims}
    issues: list[KnowledgeAtomQualityIssue] = []
    for relation in batch.relations:
        missing_claim_ids = [claim_id for claim_id in relation.source_claim_ids if claim_id not in claim_ids]
        if missing_claim_ids:
            issues.append(
                KnowledgeAtomQualityIssue(
                    issue_type="unsupported_relation",
                    severity="error",
                    atom_id=relation.id,
                    message=f"Relation references missing source claim ids: {', '.join(missing_claim_ids)}.",
                )
            )
        elif _has_foreign_evidence(batch.source_digest_id, relation.evidence):
            issues.append(
                KnowledgeAtomQualityIssue(
                    issue_type="unsupported_relation",
                    severity="error",
                    atom_id=relation.id,
                    message="Relation evidence points to a different source digest.",
                )
            )
    return issues


def _conflicting_relation_issues(relations: list[KnowledgeRelation]) -> list[KnowledgeAtomQualityIssue]:
    by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    relation_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for relation in relations:
        pair = (_object_key(relation.subject.name), _object_key(relation.object.name))
        by_pair[pair].add(relation.predicate)
        relation_ids[pair].append(relation.id)

    issues: list[KnowledgeAtomQualityIssue] = []
    for pair, predicates in by_pair.items():
        if "supports" in predicates and "contradicts" in predicates:
            issues.append(
                KnowledgeAtomQualityIssue(
                    issue_type="conflicting_relation",
                    severity="warning",
                    atom_id=", ".join(relation_ids[pair]),
                    message=f"Relation pair `{pair[0]}` -> `{pair[1]}` contains both supports and contradicts.",
                )
            )
    return issues


def _unused_entity_issues(batch: KnowledgeAtomBatch) -> list[KnowledgeAtomQualityIssue]:
    used = {_object_key(name) for claim in batch.claims for name in claim.entity_names}
    used.update(_object_key(relation.subject.name) for relation in batch.relations)
    used.update(_object_key(relation.object.name) for relation in batch.relations)

    issues: list[KnowledgeAtomQualityIssue] = []
    for entity in batch.entities:
        if _object_key(entity.name) not in used:
            issues.append(
                KnowledgeAtomQualityIssue(
                    issue_type="unused_entity",
                    severity="info",
                    atom_id=entity.atom_id,
                    message=f"Entity `{entity.name}` is not referenced by any claim or relation.",
                )
            )
    return issues


def _undefined_entity_reference_issues(batch: KnowledgeAtomBatch) -> list[KnowledgeAtomQualityIssue]:
    declared = {_object_key(entity.name) for entity in batch.entities}
    issues: list[KnowledgeAtomQualityIssue] = []
    for claim in batch.claims:
        missing = sorted(name for name in claim.entity_names if _object_key(name) not in declared)
        if missing:
            issues.append(
                KnowledgeAtomQualityIssue(
                    issue_type="undefined_entity_reference",
                    severity="error",
                    atom_id=claim.id,
                    message=f"Claim references undeclared entities: {', '.join(missing)}.",
                )
            )
    for relation in batch.relations:
        missing_relation_objects = [
            item.name
            for item in (relation.subject, relation.object)
            if _object_key(item.name) not in declared
        ]
        if missing_relation_objects:
            issues.append(
                KnowledgeAtomQualityIssue(
                    issue_type="undefined_entity_reference",
                    severity="error",
                    atom_id=relation.id,
                    message=f"Relation references undeclared entities: {', '.join(sorted(missing_relation_objects))}.",
                )
            )
    return issues


def _has_foreign_evidence(source_digest_id: str, evidence: list[KnowledgeEvidenceSpan]) -> bool:
    return any(span.source_digest_id != source_digest_id for span in evidence)


def _object_key(value: str) -> str:
    return " ".join(value.casefold().split())
