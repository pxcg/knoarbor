from __future__ import annotations

from pydantic import BaseModel, Field

from knoarbor.core.wiki_schema import normalize_page_dir
from knoarbor.semantic.ingest_workflow import IngestSemanticWorkflowResult
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
            for index, operation in enumerate(semantic_result.wiki_relation_plan.operations)
        }
        materialized_paths = {page.path for page in candidate_page_context.pages if page.exists}
        issues: list[IngestQualityGateIssue] = []

        for operation_index in approved_operation_indexes:
            draft = drafts_by_index.get(operation_index)
            if draft is None:
                issues.append(_issue(operation_index, "missing_draft", "Approved operation has no matching draft."))
                continue
            operation = operations_by_index.get(operation_index)
            if operation is None:
                issues.append(_issue(operation_index, "missing_relation_operation", "Approved draft has no matching relation operation."))
                continue
            if operation.action == "skip":
                issues.append(_issue(operation_index, "skip_has_draft", "Skip relation operation must not produce an approved draft."))
            elif draft.write_action != operation.action:
                issues.append(
                    _issue(
                        operation_index,
                        "write_action_mismatch",
                        f"Draft write_action {draft.write_action!r} does not match relation action {operation.action!r}.",
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
            if not draft.answer.strip():
                issues.append(_issue(operation_index, "missing_answer", "Draft answer/body is empty."))
            if not [item for item in draft.key_points if item.strip()]:
                issues.append(_issue(operation_index, "missing_key_points", "Draft has no key points."))
            if not [item for item in draft.tags if item.strip()]:
                issues.append(_issue(operation_index, "missing_tags", "Draft has no tags."))

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
