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
    build_fix_plan,
    lint_vault,
    render_lint_report,
    scan_vault,
    select_lint_candidates,
    write_lint_report,
)
from knoarbor.maintenance.lint_rules import is_structural_semantic_issue
from knoarbor.audit.lint_report import write_lint_run_artifacts
from knoarbor.pipelines.lint_execution import LintExecutionRouter
from knoarbor.pipelines.lint_observer import LintObserver
from knoarbor.semantic.metrics import summarize_semantic_runs
from knoarbor.runtime import current_run_monitor, vault_write_lock


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
        model diagnosis and review. Both paths are read-only with respect to
        canonical knowledge and projections.
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
        deterministic_actions = self.execution_router.collect_deterministic_actions(
            deterministic_lint.issues,
            deterministic_lint.fixes,
        )
        if mode == "deterministic":
            observer.skipped("diagnose", message="Deterministic lint mode does not run semantic diagnosis.")
            observer.skipped("review", message="Deterministic lint mode does not run model review.")
            repair_results = self.execution_router.execute(
                request.vault_path,
                deterministic_actions,
                config_path=request.config_path,
                vault_id=request.vault_id,
                provider=request.provider,
                max_tokens=request.max_tokens,
            )
            post_repair_lint = self.lint(
                WikiLintRequest(
                    vault_path=request.vault_path,
                    write_report=False,
                    scope_pages=scope_pages,
                    include_related=request.include_related,
                )
            )
            repair_results = _verify_repair_results(repair_results, post_repair_lint.issues)
            observer.finished(
                "execute",
                message=f"Executed {len(repair_results)} owner-routed repair(s).",
                payload={"repair_count": len(repair_results)},
            )
            result = LintRunResult(
                scope=request.scope,
                mode=mode,
                deterministic_lint=deterministic_lint,
                policy_decision=policy_decision,
                repair_plan=deterministic_actions,
                repair_results=repair_results,
                post_repair_lint=post_repair_lint,
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
            repair_results = self.execution_router.execute(
                request.vault_path,
                deterministic_actions,
                config_path=request.config_path,
                vault_id=request.vault_id,
                provider=request.provider,
                max_tokens=request.max_tokens,
            )
            post_repair_lint = self.lint(
                WikiLintRequest(
                    vault_path=request.vault_path,
                    write_report=False,
                    scope_pages=scope_pages,
                    include_related=request.include_related,
                )
            )
            repair_results = _verify_repair_results(repair_results, post_repair_lint.issues)
            result = LintRunResult(
                scope=request.scope,
                mode=mode,
                deterministic_lint=deterministic_lint,
                policy_decision=policy_decision,
                semantic_candidates=semantic_candidates.model_dump(),
                maintenance_review=_empty_maintenance_review("No semantic maintenance candidates to review.").model_dump(),
                repair_plan=deterministic_actions,
                repair_results=repair_results,
                post_repair_lint=post_repair_lint,
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
        repair_plan = [
            *deterministic_actions,
            *self.execution_router.build_repair_plan(semantic_candidates, maintenance_review),
        ]
        observer.started(
            "execute",
            message="Executing approved repairs through their owning lifecycle.",
            payload={"repair_plan": len(repair_plan)},
        )
        repair_results = self.execution_router.execute(
            request.vault_path,
            repair_plan,
            config_path=request.config_path,
            vault_id=request.vault_id,
            provider=request.provider,
            max_tokens=request.max_tokens,
        )
        post_repair_lint = self.lint(
            WikiLintRequest(
                vault_path=request.vault_path,
                write_report=False,
                scope_pages=scope_pages,
                include_related=request.include_related,
            )
        )
        repair_results = _verify_repair_results(repair_results, post_repair_lint.issues)
        observer.finished(
            "execute",
            message=f"Executed {len(repair_results)} owner-routed repair(s).",
            payload={"repair_count": len(repair_results)},
        )
        result = LintRunResult(
            scope=request.scope,
            mode=mode,
            deterministic_lint=deterministic_lint,
            policy_decision=policy_decision,
            semantic_candidates=semantic_candidates.model_dump(),
            maintenance_review=maintenance_review.model_dump(),
            repair_plan=repair_plan,
            repair_results=repair_results,
            post_repair_lint=post_repair_lint,
            warnings=[],
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


def _verify_repair_results(
    results: list[dict[str, object]],
    remaining_issues: list[WikiLintIssue],
) -> list[dict[str, object]]:
    remaining = {(issue.code, issue.path) for issue in remaining_issues}
    verified: list[dict[str, object]] = []
    for result in results:
        identity = (str(result.get("issue_type") or ""), str(result.get("target_page") or result.get("target") or ""))
        if result.get("status") == "completed" and identity in remaining:
            verified.append(
                {
                    **result,
                    "status": "ineffective",
                    "error": "The owning workflow completed, but the post-repair scan still reports the issue.",
                }
            )
        else:
            verified.append(result)
    return verified


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
        combined = quality
    elif not quality.candidates:
        combined = structural
    else:
        combined = _merge_candidates(structural, quality)
    return pipeline.execution_router.normalize_candidates(combined)


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
