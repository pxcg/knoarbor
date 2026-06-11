from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidate, MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview, LintMaintenanceReviewDecision
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.core.schemas.wiki_operation import WikiOperationApplyRequest, WikiOperationInput
from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteItem, WikiDraftBatchWriteRequest, WikiDraftBatchWriteResponse, WikiDraftInput
from knoarbor.maintenance.provenance_refresh import ProvenanceRefreshExecutor, ProvenanceRefreshResult
from knoarbor.pipelines.operation import WikiOperationPipeline
from knoarbor.pipelines.write import WikiWritePipeline
from knoarbor.storage.wiki_index import relative_wiki_path


class LintExecutionRouter:
    """Routes approved lint maintenance decisions to concrete executors."""

    def __init__(
        self,
        *,
        operation_pipeline: WikiOperationPipeline | None = None,
        write_pipeline: WikiWritePipeline | None = None,
        provenance_refresh: ProvenanceRefreshExecutor | None = None,
        privacy_config: PrivacyConfig | None = None,
    ) -> None:
        self.privacy_config = privacy_config or PrivacyConfig()
        self.operation_pipeline = operation_pipeline or WikiOperationPipeline(privacy_config=self.privacy_config)
        self.write_pipeline = write_pipeline or WikiWritePipeline()
        self.provenance_refresh = provenance_refresh or ProvenanceRefreshExecutor(self.write_pipeline)

    def apply_wiki_operations(
        self,
        request: LintRunRequest,
        candidates: MaintenanceCandidates,
        review: LintMaintenanceReview,
    ) -> list[dict[str, object]]:
        operations = [
            operation
            for decision in _approved_decisions(review, "supported_by_wiki_operation")
            if (operation := _candidate_to_wiki_operation(request, candidates, decision)) is not None
        ]
        if not operations:
            return []
        response = self.operation_pipeline.apply(
            WikiOperationApplyRequest(
                vault_path=request.vault_path,
                operations=operations,
            )
        )
        return [result.model_dump() for result in response.results]

    def compile_reviewed_drafts(
        self,
        semantic_workflow: object,
        request: LintRunRequest,
        candidates: MaintenanceCandidates,
        review: LintMaintenanceReview,
    ) -> WikiDraftBatch | None:
        approved = _supported_draft_write_decisions(candidates, review)
        if not approved:
            return None
        payload = {
            "maintenance_candidates": candidates.model_dump(),
            "maintenance_review": review.model_dump(),
            "approved_operations": [decision.model_dump() for decision in approved],
        }
        return semantic_workflow.compile_drafts(payload, max_tokens=request.max_tokens)

    def write_drafts(self, request: LintRunRequest, draft_batch: WikiDraftBatch) -> WikiDraftBatchWriteResponse:
        return self.write_pipeline.run(
            WikiDraftBatchWriteRequest(
                vault_path=request.vault_path,
                auto_related_links=False,
                provenance_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        wiki_draft=WikiDraftInput.model_validate(draft.model_dump()),
                        write_action=draft.write_action,
                        target_page=draft.target_page,
                        source_file=draft.source_file,
                        operation_index=draft.operation_index,
                    )
                    for draft in draft_batch.drafts
                ],
            )
        )

    def collect_queued_actions(
        self,
        candidates: MaintenanceCandidates,
        review: LintMaintenanceReview,
    ) -> list[dict[str, object]]:
        """Collect approved report-only and refresh-request decisions.

        These are intentional queue/report outputs, not failed executions. They
        preserve medium-risk maintenance intent without mutating pages.
        """

        queued: list[dict[str, object]] = []
        for decision in review.decisions:
            if decision.decision != "approve":
                continue
            if decision.executor_fit not in {"supported_by_report_only", "supported_by_refresh_request"}:
                continue
            if decision.operation_index >= len(candidates.candidates):
                continue
            candidate = candidates.candidates[decision.operation_index]
            queued.append(
                {
                    "operation_index": decision.operation_index,
                    "queue_type": "refresh_request" if decision.executor_fit == "supported_by_refresh_request" else "report_only",
                    "action": candidate.recommended_action.action,
                    "target_page": candidate.target_page,
                    "issue_type": candidate.issue_type,
                    "source": candidate.source,
                    "risk_level": decision.risk_level,
                    "confidence": min(candidate.confidence, decision.confidence),
                    "reason": decision.reason,
                    "evidence": [item.model_dump() for item in candidate.evidence],
                    "expected_effect": candidate.expected_effect,
                    "params": dict(candidate.recommended_action.params),
                    "related_pages": list(candidate.related_pages),
                    "required_followups": list(decision.required_followups),
                }
            )
        return queued

    def apply_refresh_requests(
        self,
        request: LintRunRequest,
        queued_actions: list[dict[str, object]],
    ) -> ProvenanceRefreshResult:
        return self.provenance_refresh.apply(
            vault_path=Path(request.vault_path).expanduser().resolve(),
            queued_actions=queued_actions,
        )

    @staticmethod
    def written_page_paths(request: LintRunRequest, response: WikiDraftBatchWriteResponse) -> list[str]:
        vault_path = Path(request.vault_path).expanduser().resolve()
        paths: list[str] = []
        seen: set[str] = set()
        for result in response.results:
            path = relative_wiki_path(vault_path, Path(result.wiki_file_path))
            if path in seen:
                continue
            seen.add(path)
            paths.append(path)
        return paths

    @staticmethod
    def written_page_details(request: LintRunRequest, response: WikiDraftBatchWriteResponse) -> list[dict[str, object]]:
        vault_path = Path(request.vault_path).expanduser().resolve()
        details: list[dict[str, object]] = []
        seen: set[str] = set()
        for result in response.results:
            stats = dict(result.stats)
            path = relative_wiki_path(vault_path, Path(result.wiki_file_path))
            if path in seen:
                continue
            seen.add(path)
            details.append(
                {
                    "path": path,
                    "created": bool(stats.get("created")),
                    "write_action": stats.get("write_action"),
                    "target_page": stats.get("target_page"),
                    "operation_index": stats.get("operation_index"),
                    "write_details": stats.get("write_details") if isinstance(stats.get("write_details"), dict) else {},
                }
            )
        return details


_WIKI_OPERATION_ACTIONS = {
    "rename_page",
    "merge_pages",
    "delete_page",
    "update_frontmatter",
    "replace_wikilink",
    "normalize_wikilink",
    "attach_related_pages",
    "attach_source_digest",
    "remove_related_links",
    "deduplicate_section_items",
    "remove_adjacent_duplicate_headings",
    "add_missing_section",
    "update_source_field",
    "redact_sensitive_text",
}

def _approved_decisions(review: LintMaintenanceReview, executor_fit: str) -> list[LintMaintenanceReviewDecision]:
    return [
        decision
        for decision in review.decisions
        if decision.decision == "approve" and decision.executor_fit == executor_fit
    ]


def _supported_draft_write_decisions(candidates: MaintenanceCandidates, review: LintMaintenanceReview) -> list[LintMaintenanceReviewDecision]:
    supported_actions = {
        "rewrite_section",
        "improve_summary",
        "remove_chatty_content",
        "add_contextual_links",
        "strengthen_provenance",
    }
    decisions: list[LintMaintenanceReviewDecision] = []
    for decision in _approved_decisions(review, "supported_by_draft_write"):
        if decision.operation_index >= len(candidates.candidates):
            continue
        action = candidates.candidates[decision.operation_index].recommended_action.action
        if action in supported_actions:
            decisions.append(decision)
    return decisions


def _candidate_to_wiki_operation(
    request: LintRunRequest,
    candidates: MaintenanceCandidates,
    decision: LintMaintenanceReviewDecision,
) -> WikiOperationInput | None:
    if decision.operation_index >= len(candidates.candidates):
        return None
    candidate = candidates.candidates[decision.operation_index]
    if candidate.executor_hint != "deterministic_wiki_operation":
        return None
    action = candidate.recommended_action.action
    if action not in _WIKI_OPERATION_ACTIONS:
        return None
    return _build_wiki_operation(request, candidate, decision, action)


def _build_wiki_operation(
    request: LintRunRequest,
    candidate: MaintenanceCandidate,
    decision: LintMaintenanceReviewDecision,
    action: str,
) -> WikiOperationInput:
    params = candidate.recommended_action.params
    source_file = _optional_str(params.get("source_file"))
    return WikiOperationInput(
        operation_id=candidate.candidate_id,
        action=action,
        target_page=candidate.target_page,
        reason=decision.reason,
        risk_level=decision.risk_level,
        confidence=min(candidate.confidence, decision.confidence),
        expected_effect=candidate.expected_effect,
        before_hash=_optional_str(params.get("before_hash")),
        related_pages=_string_list(params.get("related_pages")) or candidate.related_pages,
        new_path=_optional_str(params.get("new_path")),
        new_title=_optional_str(params.get("new_title")),
        old_target=_optional_str(params.get("old_target")),
        new_target=_optional_str(params.get("new_target")),
        link_text=_optional_str(params.get("link_text")),
        section=_optional_str(params.get("section")),
        section_content=_optional_str(params.get("section_content")),
        source_file=source_file,
        source_pages=_string_list(params.get("source_pages")),
        frontmatter={str(key): str(value) for key, value in _dict(params.get("frontmatter")).items()},
        archive_sources=bool(params.get("archive_sources", True)),
    )


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict(value: object) -> dict[object, object]:
    return value if isinstance(value, dict) else {}
