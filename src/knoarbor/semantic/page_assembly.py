from __future__ import annotations

from dataclasses import dataclass
import re

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeClaim, KnowledgeEvidenceSpan, KnowledgeRelation
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan
from knoarbor.semantic.knowledge_atom_closure import close_operation_atoms


@dataclass(frozen=True)
class PageAssemblyPayload:
    """Deterministic draft scaffold for the page assembly stage."""

    operations: list[dict[str, object]]
    warnings: list[str]

    def model_dump(self) -> dict[str, object]:
        return {
            "schema_version": "page_assembly.v1",
            "operations": self.operations,
            "warnings": self.warnings,
        }


def build_page_assembly_payload(
    knowledge_atom_batch: KnowledgeAtomBatch | None,
    wiki_page_plan: WikiPagePlan,
) -> dict[str, object]:
    """Build canonical page body material from page-plan selections.

    Page planning decides which claims belong to which page. Atom closure decides
    which entities, relations, evidence spans, and source digest ids follow from
    those claims. This service turns that closed material into a stable scaffold
    for draft compilation so the LLM does not rediscover page structure.
    """

    if knowledge_atom_batch is None:
        return PageAssemblyPayload(operations=[], warnings=["knowledge_atom_batch_missing"]).model_dump()

    claims_by_id = {claim.id: claim for claim in knowledge_atom_batch.claims}
    relations_by_id = {relation.id: relation for relation in knowledge_atom_batch.relations}
    operations: list[dict[str, object]] = []
    warnings: list[str] = []

    for index, operation in enumerate(wiki_page_plan.operations):
        if operation.action == "skip":
            continue
        closure = close_operation_atoms(knowledge_atom_batch, operation)
        op_warnings = [issue.code for issue in closure.issues]
        warnings.extend(f"operation:{index}:{issue.code}:{issue.atom_id or ''}" for issue in closure.issues)
        claim_number_by_id: dict[str, str] = {}
        claims: list[dict[str, object]] = []
        for claim_index, claim_id in enumerate(closure.claim_ids, start=1):
            claim = claims_by_id.get(claim_id)
            if claim is None:
                continue
            claim_number = f"C{claim_index}"
            claim_number_by_id[claim.id] = claim_number
            claims.append(
                {
                    "claim_id": claim.id,
                    "number": claim_number,
                    "text": _claim_text(claim, claim_number),
                    "claim_type": claim.claim_type,
                    "stance": claim.stance,
                    "entity_names": list(claim.entity_names),
                    "confidence": claim.confidence,
                    "evidence": [_evidence_row(claim_number, span, claim.confidence) for span in claim.evidence],
                }
            )

        relations = [
            _relation_row(relations_by_id[relation_id], claim_number_by_id)
            for relation_id in closure.relation_ids
            if relation_id in relations_by_id
        ]
        evidence = [
            row
            for claim in claims
            for row in claim.get("evidence", [])
            if isinstance(row, dict)
        ]
        operations.append(
            {
                "operation_index": index,
                "action": operation.action,
                "target_page": operation.target_page,
                "title": operation.title,
                "knowledge_object": operation.knowledge_object,
                "page_dir": operation.page_dir,
                "canonical_path": operation.canonical_path,
                "page_kind": operation.page_kind,
                "subject_kind": operation.subject_kind,
                "facets": list(operation.facets),
                "source_digest_ids": list(closure.source_digest_ids),
                "atom_ids": list(closure.atom_ids),
                "claims": claims,
                "entities": [f"[[{name}]]" for name in closure.entity_names],
                "relations": relations,
                "evidence": evidence,
                "warnings": op_warnings,
            }
        )

    return PageAssemblyPayload(operations=operations, warnings=warnings).model_dump()


def _claim_text(claim: KnowledgeClaim, claim_number: str) -> str:
    return f"{claim_number}. {_link_entities(claim.claim, claim.entity_names)}"


def _link_entities(text: str, entity_names: list[str]) -> str:
    linked = text.strip()
    for name in sorted((name.strip() for name in entity_names if name.strip()), key=len, reverse=True):
        marker = f"[[{name}]]"
        if marker in linked:
            continue
        linked = re.sub(re.escape(name), marker, linked, count=1, flags=re.IGNORECASE)
    return linked


def _relation_row(relation: KnowledgeRelation, claim_number_by_id: dict[str, str]) -> dict[str, object]:
    based_on = [claim_number_by_id[claim_id] for claim_id in relation.source_claim_ids if claim_id in claim_number_by_id]
    return {
        "relation_id": relation.id,
        "triple": f"[[{relation.subject.name}]] | {relation.predicate} | [[{relation.object.name}]] | {', '.join(based_on)}",
        "subject": relation.subject.name,
        "predicate": relation.predicate,
        "object": relation.object.name,
        "based_on": based_on,
        "confidence": relation.confidence,
        "reason": relation.reason,
    }


def _evidence_row(claim_number: str, span: KnowledgeEvidenceSpan, claim_confidence: float) -> dict[str, object]:
    return {
        "claim": claim_number,
        "source": span.source_digest_id,
        "range": _evidence_range(span),
        "basis": _compact_excerpt(span.excerpt),
        "confidence": _confidence_label(claim_confidence),
        "source_path": span.source_path,
        "source_unit_index": span.source_unit_index,
        "excerpt_hash": span.excerpt_hash,
    }


def _evidence_range(span: KnowledgeEvidenceSpan) -> str:
    if span.source_unit_index is not None:
        return f"unit:{span.source_unit_index}"
    if span.char_start is not None and span.char_end is not None:
        return f"chars:{span.char_start}-{span.char_end}"
    if span.excerpt_hash:
        return f"excerpt:{span.excerpt_hash}"
    return "evidence"


def _compact_excerpt(text: str, *, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"
