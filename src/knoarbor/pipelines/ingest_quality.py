from __future__ import annotations

from pydantic import BaseModel, Field

from knoarbor.core.wiki_schema import normalize_page_dir
from knoarbor.semantic.ingest_workflow import IngestSemanticWorkflowResult
from knoarbor.semantic.knowledge_atom_closure import close_operation_atoms
from knoarbor.semantic.knowledge_atom_quality import evaluate_knowledge_atoms
from knoarbor.pipelines.ingest_context import IngestCandidatePageContext


class IngestQualityGateIssue(BaseModel):
    operation_index: int
    code: str
    message: str


class IngestQualityGateResult(BaseModel):
    passed: bool
    approved_operation_indexes: list[int] = Field(default_factory=list)
    issues: list[IngestQualityGateIssue] = Field(default_factory=list)


class IngestQualityGate:
    """Deterministic hard checks before wiki drafts are written."""

    def validate(
        self,
        semantic_result: IngestSemanticWorkflowResult,
        approved_operation_indexes: list[int],
        *,
        candidate_page_context: IngestCandidatePageContext,
    ) -> IngestQualityGateResult:
        drafts_by_index = {draft.operation_index: draft for draft in semantic_result.wiki_draft_batch.drafts}
        operations_by_index = {
            index: operation
            for index, operation in enumerate(semantic_result.wiki_page_plan.operations)
        }
        materialized_paths = {page.path for page in candidate_page_context.pages if page.exists}
        issues: list[IngestQualityGateIssue] = []
        atom_batch = semantic_result.knowledge_atom_batch
        atom_quality = evaluate_knowledge_atoms(semantic_result.knowledge_atom_batch)
        for issue_item in atom_quality.issues:
            if issue_item.severity == "error":
                issues.append(
                    _issue(
                        -1,
                        f"knowledge_atom_{issue_item.issue_type}",
                        f"{issue_item.atom_id or semantic_result.knowledge_atom_batch.source_digest_id}: {issue_item.message}",
                    )
                )

        for operation_index in approved_operation_indexes:
            draft = drafts_by_index.get(operation_index)
            if draft is None:
                issues.append(_issue(operation_index, "missing_draft", "Approved operation has no matching draft."))
                continue
            operation = operations_by_index.get(operation_index)
            if operation is None:
                issues.append(_issue(operation_index, "missing_relation_operation", "Approved draft has no matching page plan operation."))
                continue
            if operation.action == "skip":
                issues.append(_issue(operation_index, "skip_has_draft", "Skip page plan operation must not produce an approved draft."))
            elif draft.write_action != operation.action:
                issues.append(
                    _issue(
                        operation_index,
                        "write_action_mismatch",
                        f"Draft write_action {draft.write_action!r} does not match relation action {operation.action!r}.",
                    )
                )

            closure = close_operation_atoms(atom_batch, operation)
            for closure_issue in closure.issues:
                if closure_issue.code == "relation_selected_without_source_claim":
                    issues.append(_issue(operation_index, closure_issue.code, closure_issue.message))
            expected_atom_ids = {
                *operation.selected_claim_ids,
                *operation.selected_relation_ids,
                *closure.relation_ids,
            }
            if operation.page_dir != "sources" and not operation.selected_claim_ids:
                issues.append(
                    _issue(
                        operation_index,
                        "missing_operation_claim_trace",
                        "Non-source page plan operation must select at least one claim atom id; relation atoms are auxiliary.",
                    )
                )
            if expected_atom_ids and not expected_atom_ids.issubset(set(draft.atom_ids)):
                missing = sorted(expected_atom_ids.difference(set(draft.atom_ids)))
                issues.append(
                    _issue(
                        operation_index,
                        "missing_selected_atom_trace",
                        f"Draft is missing selected atom ids from the page plan: {', '.join(missing)}.",
                    )
                )
            expected_source_digest_ids = set(closure.source_digest_ids)
            if expected_source_digest_ids and not expected_source_digest_ids.issubset(set(draft.source_digest_ids)):
                missing = sorted(expected_source_digest_ids.difference(set(draft.source_digest_ids)))
                issues.append(
                    _issue(
                        operation_index,
                        "missing_source_digest_trace",
                        f"Draft is missing source digest ids from the page plan: {', '.join(missing)}.",
                    )
                )
            if not operation.source_digest_ids:
                issues.append(
                    _issue(
                        operation_index,
                        "missing_operation_source_digest_trace",
                        "Page plan operation has no source digest trace.",
                    )
                )
            if not draft.source_digest_ids:
                issues.append(
                    _issue(
                        operation_index,
                        "missing_draft_source_digest_trace",
                        "Approved draft has no source digest trace.",
                    )
                )
            if operation.page_dir != "sources" and not expected_atom_ids:
                issues.append(
                    _issue(
                        operation_index,
                        "missing_operation_atom_trace",
                        "Non-source page plan operation has no selected claim or relation atom ids.",
                    )
                )
            if draft.page_dir != "sources" and not draft.atom_ids:
                issues.append(
                    _issue(
                        operation_index,
                        "missing_draft_atom_trace",
                        "Approved non-source draft has no atom trace.",
                    )
                )

            try:
                normalize_page_dir(draft.page_dir)
            except ValueError as exc:
                issues.append(_issue(operation_index, "invalid_page_dir", str(exc)))

            if not draft.source_file:
                issues.append(_issue(operation_index, "missing_source_file", "Draft has no source file provenance."))

            if not draft.summary.strip():
                issues.append(_issue(operation_index, "missing_summary", "Draft summary is empty."))
            if not _nonempty_items(draft.claims):
                issues.append(_issue(operation_index, "missing_claims", "Draft has no auditable claims."))
            if draft.page_dir != "sources" and len(_nonempty_items(draft.claims)) < len(operation.selected_claim_ids):
                issues.append(
                    _issue(
                        operation_index,
                        "selected_claim_not_projected",
                        "Draft must project each selected claim atom into the numbered Claims section.",
                    )
                )
            if not draft.synthesis.strip():
                issues.append(_issue(operation_index, "missing_synthesis", "Draft synthesis is empty."))
            claim_ids = _claim_ids(draft.claims)
            evidence_claims, evidence_issues = _evidence_claims(draft.evidence, draft.page_dir)
            relation_claims, relation_issues = _relation_claims(draft.relations)
            for code, message in [*evidence_issues, *relation_issues]:
                issues.append(_issue(operation_index, code, message))
            if draft.page_dir != "sources" and not evidence_claims:
                issues.append(_issue(operation_index, "missing_evidence", "Non-source drafts must include explicit evidence rows."))
            for claim_id in sorted(claim_ids.difference(evidence_claims)):
                issues.append(_issue(operation_index, "claim_without_evidence", f"Claim {claim_id} has no matching evidence row."))
            for claim_id in sorted(evidence_claims.difference(claim_ids)):
                issues.append(_issue(operation_index, "evidence_without_claim", f"Evidence references missing claim {claim_id}."))
            for claim_id in sorted(relation_claims.difference(claim_ids)):
                issues.append(_issue(operation_index, "relation_without_claim", f"Relation references missing claim {claim_id}."))

            if draft.write_action == "create":
                if draft.target_page:
                    issues.append(_issue(operation_index, "create_has_target", "Create draft must not set target_page."))
            else:
                if not draft.target_page:
                    issues.append(_issue(operation_index, "missing_target_page", f"{draft.write_action} draft requires target_page."))
                if not draft.patches:
                    issues.append(_issue(operation_index, "missing_patches", f"{draft.write_action} draft requires patches."))
                if draft.target_page and draft.target_page not in materialized_paths:
                    issues.append(
                        _issue(
                            operation_index,
                            "target_not_materialized",
                            f"{draft.write_action} target page was not materialized for safe patch review: {draft.target_page}",
                        )
                    )

        return IngestQualityGateResult(
            passed=not issues,
            approved_operation_indexes=list(approved_operation_indexes) if not issues else [],
            issues=issues,
        )


def _issue(operation_index: int, code: str, message: str) -> IngestQualityGateIssue:
    return IngestQualityGateIssue(operation_index=operation_index, code=code, message=message)


def _nonempty_items(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item.strip()]


def _claim_ids(claims: list[str]) -> set[str]:
    ids: set[str] = set()
    for index, claim in enumerate(_nonempty_items(claims), start=1):
        text = claim.strip()
        prefix = text.split(":", 1)[0].split(".", 1)[0].split("：", 1)[0].strip()
        if prefix.upper().startswith("C") and prefix[1:].isdigit():
            ids.add(f"C{int(prefix[1:])}")
        else:
            ids.add(f"C{index}")
    return ids


def _evidence_claims(evidence: list[str], page_dir: str) -> tuple[set[str], list[tuple[str, str]]]:
    claim_ids: set[str] = set()
    issues: list[tuple[str, str]] = []
    for row in _nonempty_items(evidence):
        parts = [part.strip() for part in row.split("|")]
        if len(parts) < 5:
            issues.append(("malformed_evidence", f"Evidence row must use `Claim | Source | Range | Basis | Confidence`: {row}"))
            continue
        claim_id, _source, source_range, _basis, confidence = parts[:5]
        normalized_claim = _normalize_claim_id(claim_id)
        if not normalized_claim:
            issues.append(("malformed_evidence_claim", f"Evidence row has invalid claim id: {row}"))
        else:
            claim_ids.add(normalized_claim)
        if confidence.lower() not in {"high", "medium", "low"}:
            issues.append(("invalid_evidence_confidence", f"Evidence confidence must be high, medium, or low: {row}"))
        if page_dir != "sources" and source_range.strip().lower() == "source-level":
            issues.append(("source_level_evidence_on_knowledge_page", f"Non-source evidence must point to a narrower range than source-level: {row}"))
    return claim_ids, issues


def _relation_claims(relations: list[str]) -> tuple[set[str], list[tuple[str, str]]]:
    claim_ids: set[str] = set()
    issues: list[tuple[str, str]] = []
    for row in _nonempty_items(relations):
        parts = [part.strip() for part in row.split("|")]
        if len(parts) < 4:
            issues.append(("malformed_relation", f"Relation row must use `Subject | Predicate | Object | Based on`: {row}"))
            continue
        based_on = parts[3]
        row_claims = [_normalize_claim_id(item) for item in based_on.replace("，", ",").split(",")]
        valid_claims = [item for item in row_claims if item]
        if not valid_claims:
            issues.append(("relation_missing_claim", f"Relation row must reference at least one claim id: {row}"))
        claim_ids.update(valid_claims)
    return claim_ids, issues


def _normalize_claim_id(value: str) -> str | None:
    text = value.strip().upper()
    if text.startswith("C") and text[1:].isdigit():
        return f"C{int(text[1:])}"
    return None
