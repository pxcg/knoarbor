from __future__ import annotations

from pathlib import Path
import time

from knoarbor.core.errors import InvalidConfig
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
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
from knoarbor.audit.lint_report import write_lint_run_artifacts
from knoarbor.maintenance.operation_verification import verify_lint_post_fixes
from knoarbor.pipelines.lint_execution import LintExecutionRouter
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
    ) -> None:
        self.semantic_workflow = semantic_workflow
        self.execution_router = execution_router or LintExecutionRouter()

    def scan(self, request: WikiScanRequest) -> WikiScanResponse:
        monitor = current_run_monitor()
        if monitor:
            monitor.event("scan_started", stage="scan", message="Running deterministic wiki scan.")
        vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
        pages, issues, stats = scan_vault(
            vault_path,
            request.max_chars_per_page,
            request.scope_pages,
            request.include_related,
        )
        fixes = build_fix_plan(issues)
        if monitor:
            monitor.event("scan_finished", stage="scan", message=f"Scan found {len(issues)} issue(s).", payload={"issues": len(issues), "fixes": len(fixes)})
        return WikiScanResponse(pages=pages, issues=issues, fixes=fixes, stats=stats)

    def select_candidates(self, request: WikiLintCandidateSelectRequest) -> WikiLintCandidateSelectResponse:
        vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
        candidates, stats, warnings = select_lint_candidates(
            vault_path,
            request.mode,
            request.max_candidates,
            request.max_chars_per_page,
        )
        return WikiLintCandidateSelectResponse(mode=request.mode, candidates=candidates, stats=stats, warnings=warnings)

    def lint(self, request: WikiLintRequest) -> WikiLintResponse:
        vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
        issues, stats = lint_vault(vault_path, request.scope_pages, request.include_related)
        fixes = build_fix_plan(issues)
        if request.apply_safe_fixes:
            with vault_write_lock(vault_path):
                logger.info("lint_safe_fixes_started issues=%s vault=%s", len(issues), vault_path)
                applied_fixes = apply_safe_fixes(vault_path, issues)
                logger.info("lint_safe_fixes_finished fixes=%s vault=%s", len(applied_fixes), vault_path)
            issues, stats = lint_vault(vault_path, request.scope_pages, request.include_related)
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

        monitor = current_run_monitor()
        started = time.perf_counter()
        if monitor:
            monitor.event("lint_started", stage="lint", message=f"Starting lint maintenance in {request.mode} mode.")
        semantic_history_start = _semantic_history_length(self.semantic_workflow)
        mode = normalize_lint_run_mode(request.mode)
        scope_pages = _scope_pages(request)
        deterministic_lint = self.lint(
            WikiLintRequest(
                obsidian_vault_path=request.obsidian_vault_path,
                write_report=False,
                apply_safe_fixes=request.apply_safe_fixes,
                scope_pages=scope_pages,
                include_related=request.include_related,
            )
        )
        if monitor:
            monitor.event(
                "deterministic_lint_finished",
                stage="lint",
                message=f"Deterministic lint found {len(deterministic_lint.issues)} issue(s).",
                payload={"issue_count": len(deterministic_lint.issues)},
            )
            monitor.raise_if_cancelled()
        policy_decision = _decide_lint_policy(deterministic_lint.issues, mode)
        if mode == "deterministic":
            result = LintRunResult(
                scope=request.scope,
                mode=mode,
                profile=request.profile,
                deterministic_lint=deterministic_lint,
                policy_decision=policy_decision,
                metrics=_lint_run_metrics(started, self.semantic_workflow, semantic_history_start),
            )
            return _write_lint_run_artifacts_if_requested(request, result)
        if mode == "semantic_structural" and not deterministic_lint.issues:
            result = LintRunResult(
                scope=request.scope,
                mode=mode,
                profile=request.profile,
                deterministic_lint=deterministic_lint,
                policy_decision=policy_decision,
                semantic_candidates=_empty_maintenance_candidates("No structural lint issues found.").model_dump(),
                maintenance_review=_empty_maintenance_review("No structural lint changes to review.").model_dump(),
                metrics=_lint_run_metrics(started, self.semantic_workflow, semantic_history_start),
            )
            return _write_lint_run_artifacts_if_requested(request, result)
        if self.semantic_workflow is None:
            raise InvalidConfig("Semantic lint mode requires a LintSemanticWorkflow.")

        semantic_candidates = _run_semantic_diagnose(self, request, mode)
        if monitor:
            monitor.event(
                "semantic_candidates_ready",
                stage="semantic_review",
                message=f"Prepared {len(semantic_candidates.candidates)} maintenance candidate(s).",
                payload={"candidate_count": len(semantic_candidates.candidates)},
            )
            monitor.raise_if_cancelled()
        maintenance_review = self.semantic_workflow.review(
            {
                "maintenance_candidates": semantic_candidates.model_dump(),
                "items": [candidate.model_dump() for candidate in semantic_candidates.candidates],
            },
            max_tokens=request.max_tokens,
        )
        if monitor:
            monitor.event(
                "maintenance_review_finished",
                stage="semantic_review",
                message=f"Reviewed {len(maintenance_review.decisions)} maintenance decision(s).",
                payload={"decision_count": len(maintenance_review.decisions)},
            )
            monitor.raise_if_cancelled()
        applied_operations: list[dict[str, object]] = []
        queued_actions = self.execution_router.collect_queued_actions(semantic_candidates, maintenance_review)
        written_pages: list[str] = []
        written_page_details: list[dict[str, object]] = []
        verifications: list[dict[str, object]] = []
        rescan: WikiLintResponse | None = None
        draft_batch = None
        draft_write_response = None
        if request.auto_apply_reviewed_changes:
            if monitor:
                monitor.event("reviewed_apply_started", status="writing", stage="execute", message="Applying approved maintenance changes.")
            applied_operations = self.execution_router.apply_wiki_operations(request, semantic_candidates, maintenance_review)
            draft_batch = self.execution_router.compile_reviewed_drafts(self.semantic_workflow, request, semantic_candidates, maintenance_review)
            if draft_batch is not None:
                draft_write_response = self.execution_router.write_drafts(request, draft_batch)
                written_pages = self.execution_router.written_page_paths(request, draft_write_response)
                written_page_details = self.execution_router.written_page_details(request, draft_write_response)
            raw_verifications = verify_lint_post_fixes(
                Path(request.obsidian_vault_path).expanduser().resolve(),
                applied_operations=applied_operations,
                draft_batch=draft_batch,
                draft_write_response=draft_write_response,
                candidates=semantic_candidates,
            )
            verifications = [item.model_dump() for item in raw_verifications]
            if applied_operations or written_pages:
                if monitor:
                    monitor.event("rescan_started", status="linting", stage="rescan", message="Rescanning after maintenance changes.")
                rescan = self.lint(
                    WikiLintRequest(
                        obsidian_vault_path=request.obsidian_vault_path,
                        write_report=False,
                        apply_safe_fixes=False,
                        scope_pages=_scope_pages(request),
                        include_related=request.include_related,
                    )
                )
                if monitor:
                    monitor.event("rescan_finished", status="running", stage="rescan", message=f"Rescan found {len(rescan.issues)} issue(s).", payload={"issue_count": len(rescan.issues)})
        result = LintRunResult(
            scope=request.scope,
            mode=mode,
            profile=request.profile,
            deterministic_lint=deterministic_lint,
            policy_decision=policy_decision,
            semantic_candidates=semantic_candidates.model_dump(),
            maintenance_review=maintenance_review.model_dump(),
            queued_actions=queued_actions,
            written_pages=written_pages,
            written_page_details=written_page_details,
            applied_operations=applied_operations,
            verifications=verifications,
            rescan=rescan,
            warnings=_verification_warnings(verifications),
            metrics=_lint_run_metrics(started, self.semantic_workflow, semantic_history_start),
        )
        return _write_lint_run_artifacts_if_requested(request, result)


_STRUCTURAL_SEMANTIC_CODES = {
    "broken_wikilink",
    "claim_invalid_confidence",
    "claim_missing_confidence",
    "claim_missing_evidence_section",
    "duplicate_content_hash",
    "duplicate_title",
    "frontmatter_type_mismatch",
    "knowledge_missing_source_digest_link",
    "knowledge_without_source_digest",
    "missing_frontmatter",
    "missing_frontmatter_keys",
    "missing_required_section",
    "overdense_link_graph",
    "path_alias_conflict",
    "source_digest_missing_related_pages",
    "source_section_mismatch",
    "weak_link_graph",
}


def normalize_lint_run_mode(mode: LintRunMode) -> LintRunMode:
    if mode == "structural":
        return "semantic_structural"
    if mode == "quality":
        return "semantic_quality"
    if mode == "full":
        return "semantic_full"
    return mode


def _scope_pages(request: LintRunRequest) -> list[str]:
    seen: set[str] = set()
    pages: list[str] = []
    for page in [*request.scope.changed_pages, *request.scope.neighbor_pages]:
        if page and page not in seen:
            seen.add(page)
            pages.append(page)
    return pages


def _decide_lint_policy(issues: list[WikiLintIssue], requested_mode: LintRunMode) -> LintPolicyDecision:
    if not issues:
        return LintPolicyDecision(
            triggered=False,
            mode=requested_mode,
            recommended_mode="deterministic",
        )

    semantic_reasons = _semantic_trigger_reasons(issues)
    recommended_mode: LintRunMode = "semantic_structural" if semantic_reasons else "deterministic"
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
    for issue in issues:
        if issue.code not in _STRUCTURAL_SEMANTIC_CODES:
            continue
        reason = f"{issue.code} in {issue.path}"
        if reason not in seen:
            seen.add(reason)
            reasons.append(reason)
    return reasons


def _run_semantic_diagnose(pipeline: WikiLintPipeline, request: LintRunRequest, mode: LintRunMode) -> MaintenanceCandidates:
    if mode == "semantic_structural":
        scan = pipeline.scan(
            WikiScanRequest(
                obsidian_vault_path=request.obsidian_vault_path,
                max_chars_per_page=request.max_chars_per_page,
                scope_pages=_scope_pages(request),
                include_related=request.include_related,
            )
        )
        return pipeline.semantic_workflow.diagnose_structural(_structural_diagnose_payload(scan), max_tokens=request.max_tokens)

    if mode == "semantic_quality":
        selected = pipeline.select_candidates(
            WikiLintCandidateSelectRequest(
                obsidian_vault_path=request.obsidian_vault_path,
                mode="quality",
                max_candidates=request.max_candidates,
                max_chars_per_page=request.max_chars_per_page,
            )
        )
        return pipeline.semantic_workflow.diagnose_quality({"selected_pages": selected.model_dump()}, max_tokens=request.max_tokens)

    structural_scan = pipeline.scan(
        WikiScanRequest(
            obsidian_vault_path=request.obsidian_vault_path,
            max_chars_per_page=request.max_chars_per_page,
            scope_pages=_scope_pages(request),
            include_related=request.include_related,
        )
    )
    structural = pipeline.semantic_workflow.diagnose_structural(_structural_diagnose_payload(structural_scan), max_tokens=request.max_tokens)
    selected = pipeline.select_candidates(
        WikiLintCandidateSelectRequest(
            obsidian_vault_path=request.obsidian_vault_path,
            mode="quality",
            max_candidates=request.max_candidates,
            max_chars_per_page=request.max_chars_per_page,
        )
    )
    quality = pipeline.semantic_workflow.diagnose_quality({"selected_pages": selected.model_dump()}, max_tokens=request.max_tokens)
    return _merge_candidates(structural, quality)


def _merge_candidates(*items: MaintenanceCandidates) -> MaintenanceCandidates:
    candidates = []
    page_reviews = []
    warnings: list[str] = []
    summaries: list[str] = []
    for item in items:
        candidates.extend(item.candidates)
        page_reviews.extend(item.page_reviews)
        warnings.extend(item.warnings)
        summaries.append(item.summary)
    return MaintenanceCandidates(
        candidates=candidates,
        page_reviews=page_reviews,
        summary=" ".join(summary for summary in summaries if summary).strip() or "No semantic lint candidates.",
        warnings=warnings,
    )


def _structural_diagnose_payload(scan: WikiScanResponse) -> dict[str, object]:
    issue_paths = {issue.path for issue in scan.issues}
    pages = [
        {
            "path": page.path,
            "directory": page.directory,
            "title": page.title,
            "page_type": page.page_type,
            "status": page.status,
            "source": page.source,
            "headings": page.headings,
        }
        for page in scan.pages
        if page.path in issue_paths
    ]
    return {
        "scan": {
            "issues": [issue.model_dump() for issue in scan.issues],
            "fixes": [fix.model_dump() for fix in scan.fixes],
            "stats": scan.stats,
            "pages": pages,
        }
    }


def _empty_maintenance_candidates(summary: str) -> MaintenanceCandidates:
    return MaintenanceCandidates(candidates=[], page_reviews=[], summary=summary, warnings=[])


def _empty_maintenance_review(summary: str) -> LintMaintenanceReview:
    return LintMaintenanceReview(decisions=[], summary=summary, warnings=[])


def _write_lint_run_artifacts_if_requested(request: LintRunRequest, result: LintRunResult) -> LintRunResult:
    if not request.write_report and not request.append_ledger:
        return result
    vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
    monitor = current_run_monitor()
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
