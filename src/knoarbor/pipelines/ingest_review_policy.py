from __future__ import annotations

from dataclasses import dataclass, field

from knoarbor.core.schemas.ingest_review import (
    IngestDraftReview,
    IngestDraftReviewDecision,
    IngestReviewChecks,
    IngestReviewDimensionScores,
)
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomQualityReport
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan


@dataclass(frozen=True)
class IngestReviewPolicyDecision:
    should_review: bool
    triggers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    operation_indexes: list[int] = field(default_factory=list)

    def as_context(self) -> dict[str, object]:
        return {
            "should_review": self.should_review,
            "triggers": list(self.triggers),
            "reasons": list(self.reasons),
            "operation_indexes": list(self.operation_indexes),
        }


class IngestDraftReviewPolicy:
    """Decides whether draft review needs another model call."""

    def evaluate(
        self,
        *,
        page_plan: WikiPagePlan,
        draft_batch: WikiDraftBatch,
        atom_quality: KnowledgeAtomQualityReport,
    ) -> IngestReviewPolicyDecision:
        triggers: list[str] = []
        reasons: list[str] = []
        operation_indexes: set[int] = set()

        for issue in atom_quality.issues:
            if issue.severity == "error":
                _add_trigger(
                    triggers,
                    reasons,
                    "atom_quality_error",
                    f"{issue.issue_type}: {issue.message}",
                )
            elif issue.issue_type in {"unsupported_claim", "unsupported_relation"}:
                _add_trigger(
                    triggers,
                    reasons,
                    "weak_evidence",
                    f"{issue.issue_type}: {issue.message}",
                )
            elif issue.issue_type == "conflicting_relation":
                _add_trigger(triggers, reasons, "conflict", issue.message)
            elif issue.issue_type == "duplicate_atom_id":
                _add_trigger(triggers, reasons, "duplicate", issue.message)

        if page_plan.confidence < 0.65:
            _add_trigger(triggers, reasons, "low_plan_confidence", f"page_plan confidence is {page_plan.confidence:.2f}.")

        for index, operation in enumerate(page_plan.operations):
            if operation.action == "update":
                operation_indexes.add(index)
                _add_trigger(triggers, reasons, "update", f"operation {index} updates {operation.target_page}.")
            if operation.action == "create" and operation.candidate_pages:
                operation_indexes.add(index)
                _add_trigger(
                    triggers,
                    reasons,
                    "duplicate_candidate",
                    f"operation {index} creates a page while candidate pages exist.",
                )

        for draft in draft_batch.drafts:
            if draft.write_action in {"update", "merge"}:
                operation_indexes.add(draft.operation_index)
                _add_trigger(
                    triggers,
                    reasons,
                    "update",
                    f"draft {draft.operation_index} uses write_action={draft.write_action}.",
                )
            if draft.confidence < 0.65:
                operation_indexes.add(draft.operation_index)
                _add_trigger(
                    triggers,
                    reasons,
                    "low_draft_confidence",
                    f"draft {draft.operation_index} confidence is {draft.confidence:.2f}.",
                )

        return IngestReviewPolicyDecision(
            should_review=bool(triggers),
            triggers=triggers,
            reasons=reasons,
            operation_indexes=sorted(operation_indexes),
        )


def auto_approve_ingest_draft_review(
    *,
    page_plan: WikiPagePlan,
    draft_batch: WikiDraftBatch,
    policy_decision: IngestReviewPolicyDecision,
) -> IngestDraftReview:
    decisions = [
        _auto_approved_decision(draft.operation_index, write_action=draft.write_action)
        for draft in draft_batch.drafts
        if _operation_allows_auto_approval(page_plan, draft.operation_index)
    ]
    return IngestDraftReview(
        decisions=decisions,
        batch_decision="approve" if decisions else "reject",
        summary="Draft review was skipped because deterministic policy classified the draft batch as low risk.",
        warnings=[
            "ingest_draft_review skipped by deterministic low-risk policy.",
            *policy_decision.reasons,
        ],
    )


def _operation_allows_auto_approval(page_plan: WikiPagePlan, operation_index: int) -> bool:
    if operation_index < 0 or operation_index >= len(page_plan.operations):
        return False
    return page_plan.operations[operation_index].action in {"create", "update"}


def _auto_approved_decision(operation_index: int, *, write_action: str) -> IngestDraftReviewDecision:
    write_safety = "safe_update" if write_action in {"update", "merge"} else "safe_create"
    return IngestDraftReviewDecision(
        operation_index=operation_index,
        decision="approve",
        quality_score=0.86,
        risk_level="low",
        write_safety=write_safety,
        reason="Approved by deterministic low-risk ingest review policy; write gate still performs hard validation before persistence.",
        required_changes=[],
        dimension_scores=IngestReviewDimensionScores(
            source_trace=0.86,
            atom_coverage=0.86,
            source_support=0.86,
            page_boundary=0.86,
            identity_fit=0.86,
            duplication_risk=0.86,
            relation_quality=0.86,
            synthesis_quality=0.86,
            maintainability=0.86,
            update_safety=0.86,
        ),
        checks=IngestReviewChecks(
            operation_aligned=True,
            source_trace_complete=True,
            atom_coverage_sufficient=True,
            page_boundary_clear=True,
            identity_fit=True,
            source_supported=True,
            not_duplicate=True,
            relation_quality=True,
            synthesis_quality=True,
            maintainable=True,
            update_safe=True,
            write_safe=True,
        ),
    )


def _add_trigger(triggers: list[str], reasons: list[str], trigger: str, reason: str) -> None:
    if trigger not in triggers:
        triggers.append(trigger)
    if reason not in reasons:
        reasons.append(reason)
