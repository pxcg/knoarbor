from __future__ import annotations

from pathlib import Path
import time

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.errors import InvalidConfig
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidate, MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview
from knoarbor.core.schemas.wiki_lint import (
    LintPolicyDecision,
    LintRunMode,
    LintRunRequest,
    LintRunResult,
    WikiLintCandidateSelectRequest,
    WikiLintCandidateSelectResponse,
    WikiLintIssue,
    WikiLintRequest,
    WikiLintResponse,
    WikiScanRequest,
    WikiScanResponse,
)
from knoarbor.maintenance.wiki_lint import (
    apply_safe_fixes,
    build_fix_plan,
    lint_vault,
    render_lint_report,
    scan_vault,
    select_lint_candidates,
    write_lint_report,
)
from knoarbor.maintenance.lint_rules import is_structural_semantic_issue
from knoarbor.audit.lint_report import write_lint_run_artifacts
from knoarbor.maintenance.operation_verification import verify_lint_post_fixes
from knoarbor.pipelines.lint_execution import LintExecutionRouter
from knoarbor.pipelines.lint_observer import LintObserver
from knoarbor.semantic.metrics import summarize_semantic_runs
from knoarbor.runtime import current_run_monitor, runtime_logger, vault_write_lock


logger = runtime_logger(__name__)


class WikiLintPipeline:
    """Runs deterministic and semantic wiki maintenance for an explicit scope."""

    def __init__(
        self,
        semantic_workflow: object | None = None,
        *,
        execution_router: LintExecutionRouter | None = None,
        privacy_config: PrivacyConfig | None = None,
    ) -> None:
        self.semantic_workflow = semantic_workflow
        self.privacy_config = privacy_config or PrivacyConfig()
        self.execution_router = execution_router or LintExecutionRouter(privacy_config=self.privacy_config)

    def scan(self, request: WikiScanRequest) -> WikiScanResponse:
        monitor = current_run_monitor()
        if monitor:
            monitor.event("scan_started", stage="scan", message="Running deterministic wiki scan.")
        vault_path = Path(request.vault_path).expanduser().resolve()
        pages, issues, stats = scan_vault(
            vault_path,
            request.max_chars_per_page,
            request.scope_pages,
            request.include_related,
            privacy_config=self.privacy_config,
        )
        fixes = build_fix_plan(issues)
        if monitor:
            monitor.event("scan_finished", stage="scan", message=f"Scan found {len(issues)} issue(s).", payload={"issues": len(issues), "fixes": len(fixes)})
        return WikiScanResponse(pages=pages, issues=issues, fixes=fixes, stats=stats)

    def select_candidates(self, request: WikiLintCandidateSelectRequest) -> WikiLintCandidateSelectResponse:
        vault_path = Path(request.vault_path).expanduser().resolve()
        candidates, stats, warnings = select_lint_candidates(
            vault_path,
            request.mode,
            request.max_candidates,
            request.max_chars_per_page,
            scope_pages=request.scope_pages,
            include_related=request.include_related,
            privacy_config=self.privacy_config,
        )
        return WikiLintCandidateSelectResponse(mode=request.mode, candidates=candidates, stats=stats, warnings=warnings)

    def lint(self, request: WikiLintRequest) -> WikiLintResponse:
        vault_path = Path(request.vault_path).expanduser().resolve()
        issues, stats = lint_vault(vault_path, request.scope_pages, request.include_related, privacy_config=self.privacy_config)
        fixes = build_fix_plan(issues)
        if request.apply_safe_fixes:
            with vault_write_lock(vault_path):
                logger.info("lint_safe_fixes_started issues=%s vault=%s", len(issues), vault_path)
                applied_fixes = apply_safe_fixes(
                    vault_path,
                    issues,
                    ledger_path=request.safe_fix_ledger_path,
                    privacy_config=self.privacy_config,
                )
                logger.info("lint_safe_fixes_finished fixes=%s vault=%s", len(applied_fixes), vault_path)
            issues, stats = lint_vault(vault_path, request.scope_pages, request.include_related, privacy_config=self.privacy_config)
            fixes = [*applied_fixes, *build_fix_plan(issues)]

        report_content = render_lint_report(issues, stats, fixes)
        report_path: str | None = None
        if request.write_report:
            with vault_write_lock(vault_path):
                output_path = write_lint_report(vault_path, report_content, request.report_path)
            report_path = str(output_path)

        return WikiLintResponse(
            issues=issues,
            stats=stats,
            fixes=fixes,
            report_path=report_path,
            report_content=report_content,
        )

    def run_maintenance(self, request: LintRunRequest) -> LintRunResult:
        """Run a lint maintenance pass for an explicit maintenance scope.

        The run always starts with deterministic lint. Semantic modes then add
        model diagnosis and review, and approved changes are executed only when
        the caller explicitly enables reviewed writes.
        """

        observer = LintObserver.current()
        started = time.perf_counter()
        semantic_history_start = _semantic_history_length(self.semantic_workflow)
        mode = request.mode
        scope_pages = _scope_pages(request)
        observer.started("scan", message=f"Starting lint maintenance in {request.mode} mode.")
        deterministic_lint = self.lint(
            WikiLintRequest(
                vault_path=request.vault_path,
                write_report=False,
                apply_safe_fixes=request.apply_safe_fixes,
                safe_fix_ledger_path=request.ledger_path,
                scope_pages=scope_pages,
                include_related=request.include_related,
            )
        )
        observer.finished(
            "scan",
            message=f"Deterministic lint found {len(deterministic_lint.issues)} issue(s).",
            payload={"issue_count": len(deterministic_lint.issues), "fix_count": len(deterministic_lint.fixes)},
        )
        policy_decision = _decide_lint_policy(deterministic_lint.issues, mode)
        if mode == "deterministic":
            observer.skipped("diagnose", message="Deterministic lint mode does not run semantic diagnosis.")
            observer.skipped("review", message="Deterministic lint mode does not run model review.")
            observer.skipped("execute", message="No semantic maintenance decisions to execute.")
            observer.skipped("verify", message="No semantic writes require verification.")
            result = LintRunResult(
                scope=request.scope,
                mode=mode,
                deterministic_lint=deterministic_lint,
                policy_decision=policy_decision,
                metrics=_lint_run_metrics(started, self.semantic_workflow, semantic_history_start),
            )
            return _write_lint_run_artifacts_if_requested(request, result, observer)
        if self.semantic_workflow is None:
            raise InvalidConfig("Semantic lint mode requires a LintSemanticWorkflow.")

        observer.started("diagnose", message="Preparing semantic maintenance candidates.")
        semantic_candidates = _run_semantic_diagnose(self, request)
        observer.finished(
            "diagnose",
            message=f"Prepared {len(semantic_candidates.candidates)} maintenance candidate(s).",
            payload={"candidate_count": len(semantic_candidates.candidates)},
        )
        if not semantic_candidates.candidates:
            observer.skipped("review", message="No semantic maintenance candidates to review.")
            observer.skipped("execute", message="No reviewed maintenance decisions to execute.")
            observer.skipped("verify", message="No semantic writes require verification.")
            result = LintRunResult(
                scope=request.scope,
                mode=mode,
                deterministic_lint=deterministic_lint,
                policy_decision=policy_decision,
                semantic_candidates=semantic_candidates.model_dump(),
                maintenance_review=_empty_maintenance_review("No semantic maintenance candidates to review.").model_dump(),
                metrics=_lint_run_metrics(started, self.semantic_workflow, semantic_history_start),
            )
            return _write_lint_run_artifacts_if_requested(request, result, observer)
        observer.started("review", message="Reviewing semantic maintenance candidates.")
        maintenance_review = self.semantic_workflow.review(
            _maintenance_review_payload(semantic_candidates),
            max_tokens=request.max_tokens,
        )
        observer.finished(
            "review",
            message=f"Reviewed {len(maintenance_review.decisions)} maintenance decision(s).",
            payload={"decision_count": len(maintenance_review.decisions)},
        )
        applied_operations: list[dict[str, object]] = []
        queued_actions = self.execution_router.collect_queued_actions(semantic_candidates, maintenance_review)
        written_pages: list[str] = []
        written_page_details: list[dict[str, object]] = []
        verifications: list[dict[str, object]] = []
        deferred_retries: list[dict[str, object]] = []
        refresh_warnings: list[str] = []
        rescan: WikiLintResponse | None = None
        draft_batch = None
        draft_write_response = None
        if request.auto_apply_reviewed_changes:
            observer.started("execute", message="Applying approved maintenance changes.")
            applied_operations = self.execution_router.apply_wiki_operations(request, semantic_candidates, maintenance_review)
            draft_batch = self.execution_router.compile_reviewed_drafts(self.semantic_workflow, request, semantic_candidates, maintenance_review)
            if draft_batch is not None:
                draft_write_response = self.execution_router.write_drafts(request, draft_batch)
                written_pages = self.execution_router.written_page_paths(request, draft_write_response)
                written_page_details = self.execution_router.written_page_details(request, draft_write_response)
            observer.finished(
                "execute",
                message=f"Applied {len(applied_operations)} operation(s) and wrote {len(written_pages)} page(s).",
                payload={"applied_operations": len(applied_operations), "written_pages": len(written_pages), "queued_actions": len(queued_actions)},
            )
            observer.started("verify", message="Verifying reviewed maintenance changes.")
            raw_verifications = verify_lint_post_fixes(
                Path(request.vault_path).expanduser().resolve(),
                applied_operations=applied_operations,
                draft_batch=draft_batch,
                draft_write_response=draft_write_response,
                candidates=semantic_candidates,
                privacy_config=self.privacy_config,
            )
            verifications = [item.model_dump() for item in raw_verifications]
            if applied_operations or written_pages:
                rescan = self.lint(
                    WikiLintRequest(
                        vault_path=request.vault_path,
                        write_report=False,
                        apply_safe_fixes=False,
                        scope_pages=_scope_pages(request),
                        include_related=request.include_related,
                    )
                )
            observer.finished(
                "verify",
                message=f"Verification produced {len(verifications)} result(s).",
                payload={"verification_count": len(verifications), "rescan_issue_count": len(rescan.issues) if rescan else None},
            )
        else:
            observer.skipped("execute", message="Reviewed maintenance writes are disabled.")
            observer.skipped("verify", message="No reviewed writes require verification.")
        if request.auto_apply_reviewed_changes and request.auto_retry_deferred_actions and request.max_deferred_retry_rounds > 0:
            retry_queue = queued_actions
            for retry_round in range(1, request.max_deferred_retry_rounds + 1):
                retry = _run_deferred_retry(self, request, retry_queue, retry_round=retry_round)
                if retry is None:
                    break
                deferred_retries.append(retry["summary"])
                queued_actions.extend(retry["queued_actions"])
                applied_operations.extend(retry["applied_operations"])
                written_pages.extend(retry["written_pages"])
                written_page_details.extend(retry["written_page_details"])
                verifications.extend(retry["verifications"])
                if not retry["queued_actions"] or not (retry["applied_operations"] or retry["written_pages"]):
                    break
                retry_queue = retry["queued_actions"]
                if retry["applied_operations"] or retry["written_pages"]:
                    rescan = self.lint(
                        WikiLintRequest(
                            vault_path=request.vault_path,
                            write_report=False,
                            apply_safe_fixes=False,
                            scope_pages=_scope_pages(request),
                            include_related=request.include_related,
                        )
                    )
        if request.auto_apply_reviewed_changes:
            refresh_result = self.execution_router.apply_refresh_requests(request, queued_actions)
            if refresh_result.applied_operations or refresh_result.written_pages:
                applied_operations.extend(refresh_result.applied_operations)
                written_pages.extend(refresh_result.written_pages)
                written_page_details.extend(refresh_result.written_page_details)
                refresh_verifications = verify_lint_post_fixes(
                    Path(request.vault_path).expanduser().resolve(),
                    applied_operations=refresh_result.applied_operations,
                    privacy_config=self.privacy_config,
                )
                verifications.extend(item.model_dump() for item in refresh_verifications)
                rescan = self.lint(
                    WikiLintRequest(
                        vault_path=request.vault_path,
                        write_report=False,
                        apply_safe_fixes=False,
                        scope_pages=_scope_pages(request),
                        include_related=request.include_related,
                    )
                )
            refresh_warnings.extend(refresh_result.warnings)
        result = LintRunResult(
            scope=request.scope,
            mode=mode,
            deterministic_lint=deterministic_lint,
            policy_decision=policy_decision,
            semantic_candidates=semantic_candidates.model_dump(),
            maintenance_review=maintenance_review.model_dump(),
            draft_batch=draft_batch.model_dump() if draft_batch is not None else None,
            queued_actions=queued_actions,
            deferred_retries=deferred_retries,
            written_pages=written_pages,
            written_page_details=written_page_details,
            applied_operations=applied_operations,
            verifications=verifications,
            rescan=rescan,
            warnings=[*_verification_warnings(verifications), *refresh_warnings],
            metrics=_lint_run_metrics(started, self.semantic_workflow, semantic_history_start),
        )
        return _write_lint_run_artifacts_if_requested(request, result, observer)


def _scope_pages(request: LintRunRequest) -> list[str]:
    seen: set[str] = set()
    pages: list[str] = []
    for page in [*request.scope.changed_pages, *request.scope.neighbor_pages]:
        if page and page not in seen:
            seen.add(page)
            pages.append(page)
    return pages


def _maintenance_review_payload(
    candidates: MaintenanceCandidates,
    *,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "maintenance_candidates": candidates.model_dump(),
        "items": [_review_item(index, candidate) for index, candidate in enumerate(candidates.candidates)],
    }
    if extra:
        payload.update(extra)
    return payload


def _review_item(index: int, candidate: MaintenanceCandidate) -> dict[str, object]:
    return {
        "operation_index": index,
        "candidate_id": candidate.candidate_id,
        "source": candidate.source,
        "target_page": candidate.target_page,
        "issue_type": candidate.issue_type,
        "severity": candidate.severity,
        "confidence": candidate.confidence,
        "risk_hint": candidate.risk_hint,
        "executor_hint": candidate.executor_hint,
        "recommended_action": candidate.recommended_action.model_dump(),
        "expected_effect": candidate.expected_effect,
        "review_notes": candidate.review_notes,
        "evidence_count": len(candidate.evidence),
    }


def _decide_lint_policy(issues: list[WikiLintIssue], requested_mode: LintRunMode) -> LintPolicyDecision:
    if not issues:
        return LintPolicyDecision(
            triggered=False,
            mode=requested_mode,
            recommended_mode="deterministic",
        )

    semantic_reasons = _semantic_trigger_reasons(issues)
    recommended_mode: LintRunMode = "semantic" if semantic_reasons else "deterministic"
    triggered = requested_mode != "deterministic" and recommended_mode != "deterministic"
    return LintPolicyDecision(
        triggered=triggered,
        mode=requested_mode,
        recommended_mode=recommended_mode,
        trigger_reasons=semantic_reasons,
        deferred_issue_count=0 if triggered else len([issue for issue in issues if issue.severity in {"error", "warning"}]),
    )


def _semantic_trigger_reasons(issues: list[WikiLintIssue]) -> list[str]:
    reasons: list[str] = []
    seen: set[str] = set()
    for issue in _eligible_structural_issues(issues):
        reason = f"{issue.code} in {issue.path}"
        if reason not in seen:
            seen.add(reason)
            reasons.append(reason)
    return reasons


def _eligible_structural_issues(issues: list[WikiLintIssue]) -> list[WikiLintIssue]:
    return [issue for issue in issues if is_structural_semantic_issue(issue.code)]


def _run_semantic_diagnose(pipeline: WikiLintPipeline, request: LintRunRequest) -> MaintenanceCandidates:
    structural_scan = pipeline.scan(
        WikiScanRequest(
            vault_path=request.vault_path,
            max_chars_per_page=request.max_chars_per_page,
            scope_pages=_scope_pages(request),
            include_related=request.include_related,
        )
    )
    structural_payload = _structural_diagnose_payload(structural_scan)
    structural = (
        pipeline.semantic_workflow.diagnose_structural(structural_payload, max_tokens=request.max_tokens)
        if structural_payload["scan"]["issues"]
        else _empty_maintenance_candidates("No eligible structural lint issues found.")
    )
    selected = pipeline.select_candidates(
        WikiLintCandidateSelectRequest(
            vault_path=request.vault_path,
            mode="semantic",
            max_candidates=request.max_candidates,
            max_chars_per_page=request.max_chars_per_page,
            scope_pages=_scope_pages(request),
            include_related=request.include_related,
        )
    )
    quality = (
        pipeline.semantic_workflow.diagnose_quality({"selected_pages": selected.model_dump()}, max_tokens=request.max_tokens)
        if selected.candidates
        else _empty_maintenance_candidates("No semantic quality candidates selected.")
    )
    if not structural.candidates:
        return quality
    if not quality.candidates:
        return structural
    return _merge_candidates(structural, quality)


def _run_deferred_retry(
    pipeline: WikiLintPipeline,
    request: LintRunRequest,
    queued_actions: list[dict[str, object]],
    *,
    retry_round: int,
) -> dict[str, object] | None:
    if pipeline.semantic_workflow is None:
        return None
    retry_pages = _deferred_retry_pages(queued_actions)
    if not retry_pages:
        return None
    observer = LintObserver.current()
    observer.started(
        "diagnose",
        message=f"Retrying {len(retry_pages)} deferred page(s) with enriched context.",
        payload={"page_count": len(retry_pages), "retry_round": retry_round},
    )
    retry_scope = request.scope.model_copy(
        update={
            "scope_id": f"{request.scope.scope_id}:deferred-retry",
            "trigger": "manual",
            "changed_pages": retry_pages,
            "neighbor_pages": [],
            "reason": "Automatic deferred lint retry with enriched page context.",
        }
    )
    retry_request = request.model_copy(
        update={
            "scope": retry_scope,
            "apply_safe_fixes": False,
            "auto_retry_deferred_actions": False,
        }
    )
    scan = pipeline.scan(
        WikiScanRequest(
            vault_path=retry_request.vault_path,
            max_chars_per_page=retry_request.max_chars_per_page,
            scope_pages=retry_pages,
            include_related=True,
        )
    )
    candidates = pipeline.semantic_workflow.diagnose_structural(
        _structural_diagnose_payload(scan, include_content=True),
        max_tokens=retry_request.max_tokens,
    )
    observer.finished(
        "diagnose",
        message=f"Prepared {len(candidates.candidates)} deferred retry candidate(s).",
        payload={"candidate_count": len(candidates.candidates), "retry_round": retry_round},
    )
    observer.started("review", message="Reviewing deferred retry candidates.", payload={"retry_round": retry_round})
    review = pipeline.semantic_workflow.review(
        _maintenance_review_payload(
            candidates,
            extra={
            "deferred_retry": {
                "source_queue_count": len(queued_actions),
                "retry_pages": retry_pages,
                "round": retry_round,
            },
            },
        ),
        max_tokens=retry_request.max_tokens,
    )
    observer.finished(
        "review",
        message=f"Reviewed {len(review.decisions)} deferred retry decision(s).",
        payload={"decision_count": len(review.decisions), "retry_round": retry_round},
    )
    observer.started("execute", message="Applying deferred retry maintenance changes.", payload={"retry_round": retry_round})
    applied_operations = pipeline.execution_router.apply_wiki_operations(retry_request, candidates, review)
    draft_batch = pipeline.execution_router.compile_reviewed_drafts(pipeline.semantic_workflow, retry_request, candidates, review)
    written_pages: list[str] = []
    written_page_details: list[dict[str, object]] = []
    draft_write_response = None
    if draft_batch is not None:
        draft_write_response = pipeline.execution_router.write_drafts(retry_request, draft_batch)
        written_pages = pipeline.execution_router.written_page_paths(retry_request, draft_write_response)
        written_page_details = pipeline.execution_router.written_page_details(retry_request, draft_write_response)
    observer.finished(
        "execute",
        message=f"Deferred retry applied {len(applied_operations)} operation(s) and wrote {len(written_pages)} page(s).",
        payload={"applied_operations": len(applied_operations), "written_pages": len(written_pages), "retry_round": retry_round},
    )
    observer.started("verify", message="Verifying deferred retry changes.", payload={"retry_round": retry_round})
    raw_verifications = verify_lint_post_fixes(
        Path(retry_request.vault_path).expanduser().resolve(),
        applied_operations=applied_operations,
        draft_batch=draft_batch,
        draft_write_response=draft_write_response,
        candidates=candidates,
        privacy_config=pipeline.privacy_config,
    )
    retry_queued = pipeline.execution_router.collect_queued_actions(candidates, review)
    verifications = [item.model_dump() for item in raw_verifications]
    observer.finished(
        "verify",
        message=f"Deferred retry verification produced {len(verifications)} result(s).",
        payload={"verification_count": len(verifications), "queued_actions": len(retry_queued), "retry_round": retry_round},
    )
    return {
        "summary": {
            "round": retry_round,
            "retry_pages": retry_pages,
            "candidate_count": len(candidates.candidates),
            "review_decisions": len(review.decisions),
            "queued_actions": len(retry_queued),
            "applied_operations": len(applied_operations),
            "written_pages": len(written_pages),
            "verifications": len(verifications),
        },
        "queued_actions": retry_queued,
        "applied_operations": applied_operations,
        "written_pages": written_pages,
        "written_page_details": written_page_details,
        "verifications": verifications,
    }


def _deferred_retry_pages(queued_actions: list[dict[str, object]]) -> list[str]:
    seen: set[str] = set()
    pages: list[str] = []
    for action in queued_actions:
        if action.get("queue_type") != "report_only":
            continue
        _append_page(pages, seen, action.get("target_page"))
        params = action.get("params")
        if isinstance(params, dict):
            for key in ("target_page", "old_target", "new_target"):
                _append_page(pages, seen, params.get(key))
            source_pages = params.get("source_pages")
            if isinstance(source_pages, list):
                for page in source_pages:
                    _append_page(pages, seen, page)
            pages_param = params.get("pages")
            if isinstance(pages_param, list):
                for page in pages_param:
                    _append_page(pages, seen, page)
    return pages


def _append_page(pages: list[str], seen: set[str], value: object) -> None:
    if not isinstance(value, str) or not value.endswith(".md") or value in seen:
        return
    seen.add(value)
    pages.append(value)


def _merge_candidates(*items: MaintenanceCandidates) -> MaintenanceCandidates:
    candidates = []
    page_reviews = []
    warnings: list[str] = []
    summaries: list[str] = []
    seen_candidate_ids: set[str] = set()
    seen_operation_identities: set[tuple[str, str, str, str, str, str]] = set()
    for item in items:
        for candidate in item.candidates:
            if candidate.candidate_id in seen_candidate_ids:
                continue
            operation_identity = _candidate_operation_identity(candidate)
            if operation_identity in seen_operation_identities:
                continue
            seen_candidate_ids.add(candidate.candidate_id)
            seen_operation_identities.add(operation_identity)
            candidates.append(candidate)
        page_reviews.extend(item.page_reviews)
        warnings.extend(item.warnings)
        summaries.append(item.summary)
    return MaintenanceCandidates(
        candidates=candidates,
        page_reviews=page_reviews,
        summary=" ".join(summary for summary in summaries if summary).strip() or "No semantic lint candidates.",
        warnings=warnings,
    )


def _candidate_operation_identity(candidate: MaintenanceCandidate) -> tuple[str, str, str, str, str, str]:
    params = candidate.recommended_action.params
    return (
        candidate.target_page,
        candidate.recommended_action.action,
        str(params.get("section") or ""),
        str(params.get("old_target") or ""),
        str(params.get("new_target") or ""),
        str(params.get("source_file") or ""),
    )


def _structural_diagnose_payload(scan: WikiScanResponse, *, include_content: bool = False) -> dict[str, object]:
    eligible_issues = _eligible_structural_issues(scan.issues)
    issue_paths = {issue.path for issue in eligible_issues}
    pages = []
    for page in scan.pages:
        if page.path not in issue_paths:
            continue
        item = {
            "path": page.path,
            "directory": page.directory,
            "title": page.title,
            "headings": page.headings,
        }
        if include_content:
            item.update(
                {
                    "summary": page.summary,
                    "entities": page.entities,
                    "outgoing_links": page.outgoing_links,
                    "content_preview": page.content_preview,
                    "content_truncated": page.content_truncated,
                    "original_content_length": page.original_content_length,
                }
            )
        pages.append(item)
    return {
        "scan": {
            "issues": [issue.model_dump() for issue in eligible_issues],
            "fixes": [fix.model_dump() for fix in scan.fixes],
            "stats": scan.stats,
            "pages": pages,
        }
    }


def _empty_maintenance_candidates(summary: str) -> MaintenanceCandidates:
    return MaintenanceCandidates(candidates=[], page_reviews=[], summary=summary, warnings=[])


def _empty_maintenance_review(summary: str) -> LintMaintenanceReview:
    return LintMaintenanceReview(decisions=[], summary=summary, warnings=[])


def _write_lint_run_artifacts_if_requested(request: LintRunRequest, result: LintRunResult, observer: LintObserver) -> LintRunResult:
    if not request.write_report and not request.append_ledger:
        observer.skipped("report", message="Lint report and ledger writing are disabled.")
        return result
    vault_path = Path(request.vault_path).expanduser().resolve()
    monitor = current_run_monitor()
    observer.started("report", message="Writing lint run artifacts.")
    ledger_path, report_path = write_lint_run_artifacts(
        vault_path,
        result,
        run_id=monitor.run_id if monitor else None,
        append_ledger=request.append_ledger,
        write_report=request.write_report,
        report_path=request.report_path,
        ledger_path=request.ledger_path,
    )
    result.ledger_path = ledger_path
    result.report_path = report_path
    observer.finished(
        "report",
        message="Lint run artifacts written.",
        payload={"ledger_path": ledger_path, "report_path": report_path},
    )
    return result


def _verification_warnings(verifications: list[dict[str, object]]) -> list[str]:
    failed = sum(1 for item in verifications if item.get("status") == "failed")
    if failed == 0:
        return []
    return [f"Post-fix verification failed for {failed} lint operation(s)."]


def _semantic_history_length(semantic_workflow: object | None) -> int:
    runner = getattr(semantic_workflow, "runner", None)
    history = getattr(runner, "history", None)
    return len(history) if isinstance(history, list) else 0


def _lint_run_metrics(started: float, semantic_workflow: object | None, history_start: int) -> dict[str, object]:
    elapsed = time.perf_counter() - started
    runner = getattr(semantic_workflow, "runner", None)
    history = getattr(runner, "history", None)
    runs = history[history_start:] if isinstance(history, list) else []
    return {
        "elapsed_seconds": elapsed,
        "semantic": summarize_semantic_runs(runs),
    }
