from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.audit.contracts import LEDGER_PATHS, LEDGER_SCHEMA_VERSIONS
from knoarbor.core.schemas.wiki_lint import LintRunResult
from knoarbor.audit.reports import write_maintenance_report
from knoarbor.audit.report_formatting import as_dict, as_list, cache_metric_lines, fmt_number, format_list, semantic_token_report_lines
from knoarbor.audit.token_ledger import append_lint_token_records
from knoarbor.storage.ledger import append_jsonl_ledger, read_jsonl_ledger
from knoarbor.storage.wiki_index import relative_wiki_path


LINT_RUN_SCHEMA_VERSION = LEDGER_SCHEMA_VERSIONS["lint"]


def write_lint_run_artifacts(
    vault_path: Path,
    result: LintRunResult,
    *,
    run_id: str | None = None,
    append_ledger: bool = True,
    write_report: bool = True,
    report_path: str | None = None,
    ledger_path: str = LEDGER_PATHS["lint"],
) -> tuple[str | None, str | None]:
    """Write compact lint run report and append-only ledger entry."""

    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    previous_records = read_jsonl_ledger(vault_path, ledger_path, limit=20) if append_ledger or write_report else []
    record = build_lint_run_record(result, run_id=run_id, previous_records=previous_records)
    written_ledger = append_jsonl_ledger(vault_path, ledger_path, record) if append_ledger else None
    if append_ledger:
        append_lint_token_records(vault_path, record)
    effective_report_path = report_path or f"maintenance/reports/lint/lint_run_report_{run_id}.md"
    written_report = (
        write_maintenance_report(vault_path, "lint_run", render_lint_run_report(record), effective_report_path)
        if write_report
        else None
    )
    return (
        relative_wiki_path(vault_path, written_ledger) if written_ledger else None,
        relative_wiki_path(vault_path, written_report) if written_report else None,
    )


def build_lint_run_record(result: LintRunResult, *, run_id: str, previous_records: list[dict[str, object]] | None = None) -> dict[str, object]:
    deterministic = result.deterministic_lint
    semantic_candidates = as_dict(result.semantic_candidates)
    review = as_dict(result.maintenance_review)
    rescan = result.rescan
    issue_summary = _issue_summary(deterministic.issues, rescan.issues if rescan else None)
    trend_summary = _trend_summary(previous_records or [], issue_summary)
    return {
        "schema_version": LINT_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scope": result.scope.model_dump(),
        "mode": result.mode,
        "policy_decision": result.policy_decision.model_dump(),
        "deterministic_lint": {
            "stats": deterministic.stats,
            "issues": [_issue_record(issue) for issue in deterministic.issues],
            "fixes": [fix.model_dump() for fix in deterministic.fixes],
        },
        "issue_summary": issue_summary,
        "trend_summary": trend_summary,
        "semantic_candidates": _semantic_candidates_record(semantic_candidates),
        "quality_review_summary": _quality_review_summary(semantic_candidates),
        "maintenance_review": _review_record(review),
        "queued_actions": result.queued_actions,
        "deferred_retries": result.deferred_retries,
        "refresh_queue": _queue_by_type(result.queued_actions, "refresh_request"),
        "governance_queue": _governance_queue(result.queued_actions),
        "applied_operations": result.applied_operations,
        "written_pages": result.written_pages,
        "written_page_details": result.written_page_details,
        "verifications": result.verifications,
        "verification_summary": _verification_summary(result.verifications),
        "operation_summary": _operation_summary(result.applied_operations, result.written_pages, result.verifications),
        "rescan": {
            "stats": rescan.stats,
            "issues": [_issue_record(issue) for issue in rescan.issues],
            "fixes": [fix.model_dump() for fix in rescan.fixes],
        }
        if rescan
        else None,
        "metrics": dict(result.metrics),
        "warnings": result.warnings,
    }


def render_lint_run_report(record: dict[str, object]) -> str:
    deterministic = as_dict(record.get("deterministic_lint"))
    deterministic_stats = as_dict(deterministic.get("stats"))
    policy = as_dict(record.get("policy_decision"))
    semantic = as_dict(record.get("semantic_candidates"))
    review = as_dict(record.get("maintenance_review"))
    rescan = as_dict(record.get("rescan"))
    rescan_stats = as_dict(rescan.get("stats"))
    issue_summary = as_dict(record.get("issue_summary"))
    trend_summary = as_dict(record.get("trend_summary"))
    graph_health = as_dict(deterministic_stats.get("graph_health"))
    quality_review_summary = as_dict(record.get("quality_review_summary"))
    operation_summary = as_dict(record.get("operation_summary"))
    verification_summary = as_dict(record.get("verification_summary"))
    metrics = as_dict(record.get("metrics"))
    semantic_metrics = as_dict(metrics.get("semantic"))
    lines = [
        "# Lint Run Report",
        "",
        f"- run_id: {record.get('run_id')}",
        f"- created_at: {record.get('created_at')}",
        f"- mode: {record.get('mode')}",
        f"- scope_id: {as_dict(record.get('scope')).get('scope_id')}",
        f"- deterministic_issues: {deterministic_stats.get('issue_count', 0)}",
        f"- deterministic_fixes: {len(as_list(deterministic.get('fixes')))}",
        f"- recommended_mode: {policy.get('recommended_mode')}",
        f"- policy_triggered: {policy.get('triggered')}",
        f"- semantic_candidates: {semantic.get('candidate_count', 0)}",
        f"- review_decisions: {review.get('decision_count', 0)}",
        f"- queued_actions: {len(as_list(record.get('queued_actions')))}",
        f"- deferred_retries: {len(as_list(record.get('deferred_retries')))}",
        f"- applied_operations: {len(as_list(record.get('applied_operations')))}",
        f"- written_pages: {len(as_list(record.get('written_pages')))}",
        f"- operation_success_rate: {fmt_number(operation_summary.get('success_rate'))}",
        f"- verifications: {verification_summary.get('verified', 0)} verified / {verification_summary.get('failed', 0)} failed / {verification_summary.get('skipped', 0)} skipped",
        f"- follow_up_required: {verification_summary.get('follow_up_required', False)}",
        f"- rescan_issues: {rescan_stats.get('issue_count', 'not_run')}",
        f"- issue_delta: {issue_summary.get('issue_delta', 'n/a')}",
        f"- trend_issue_delta_from_previous: {trend_summary.get('issue_delta_from_previous', 'n/a')}",
        f"- graph_components: {graph_health.get('component_count', 'n/a')} / largest {graph_health.get('largest_component_size', 'n/a')}",
        f"- quality_reviews: {quality_review_summary.get('page_review_count', 0)} pages / avg score {fmt_number(quality_review_summary.get('average_overall_score'))}",
        f"- elapsed_seconds: {fmt_number(metrics.get('elapsed_seconds'))}",
        f"- semantic_calls: {semantic_metrics.get('semantic_call_count', 0)}",
        f"- total_tokens: {semantic_metrics.get('total_tokens', 0)}",
        *cache_metric_lines(semantic_metrics),
        f"- tokens_per_second: {fmt_number(semantic_metrics.get('tokens_per_second'))}",
        "",
        *semantic_token_report_lines(semantic_metrics),
        "## Issue Summary",
        "",
        f"- before_rescan: {issue_summary.get('before_issue_count', 0)}",
        f"- after_rescan: {issue_summary.get('after_issue_count', 'not_run')}",
        f"- issue_delta: {issue_summary.get('issue_delta', 'n/a')}",
        f"- repeated_issue_codes: {_format_issue_counts(as_dict(issue_summary.get('before_code_counts')))}",
        "",
        "## Trend Summary",
        "",
        f"- previous_runs_considered: {trend_summary.get('previous_runs_considered', 0)}",
        f"- previous_issue_count: {trend_summary.get('previous_issue_count', 'n/a')}",
        f"- current_issue_count: {trend_summary.get('current_issue_count', 0)}",
        f"- issue_delta_from_previous: {trend_summary.get('issue_delta_from_previous', 'n/a')}",
        f"- persistent_issue_codes: {_format_issue_counts(as_dict(trend_summary.get('persistent_issue_codes')))}",
        "",
        "## Graph Health",
        "",
        f"- node_count: {graph_health.get('node_count', 0)}",
        f"- component_count: {graph_health.get('component_count', 0)}",
        f"- largest_component_size: {graph_health.get('largest_component_size', 0)}",
        f"- isolated_page_count: {graph_health.get('isolated_page_count', 0)}",
        f"- small_component_count: {graph_health.get('small_component_count', 0)}",
        f"- hub_pages: {_format_hub_pages(as_list(graph_health.get('hub_pages')))}",
        "",
        "## Deterministic Issues",
        "",
    ]
    issues = as_list(deterministic.get("issues"))
    if not issues:
        lines.append("- No deterministic issues.")
    else:
        for issue in issues[:50]:
            lines.append(f"- [{issue.get('severity')}] `{issue.get('code')}` in `{issue.get('path')}`: {issue.get('message')}")

    lines.extend(["", "## Semantic Candidates", ""])
    candidates = as_list(semantic.get("candidates"))
    if not candidates:
        lines.append("- No semantic candidates.")
    else:
        for candidate in candidates:
            lines.append(
                f"- `{candidate.get('candidate_id')}` {candidate.get('executor_hint')} "
                f"{candidate.get('recommended_action')} -> {candidate.get('target_page')}"
            )

    if quality_review_summary:
        lines.extend(["", "## Quality Reviews", ""])
        lines.append(f"- reviewed_pages: {quality_review_summary.get('page_review_count', 0)}")
        lines.append(f"- average_overall_score: {fmt_number(quality_review_summary.get('average_overall_score'))}")
        low_score_pages = as_list(quality_review_summary.get("low_score_pages"))
        if low_score_pages:
            lines.append("- low_score_pages:")
            lines.extend(f"  - `{page}`" for page in low_score_pages[:20])

    lines.extend(["", "## Review Decisions", ""])
    decisions = as_list(review.get("decisions"))
    if not decisions:
        lines.append("- No review decisions.")
    else:
        for decision in decisions:
            lines.append(
                f"- [{decision.get('decision')}] operation {decision.get('operation_index')} "
                f"{decision.get('executor_fit')} risk={decision.get('risk_level')}: {decision.get('reason')}"
            )

    lines.extend(["", "## Queued Actions", ""])
    queued_actions = as_list(record.get("queued_actions"))
    if not queued_actions:
        lines.append("- No queued report-only or refresh-request actions.")
    else:
        for item in queued_actions:
            lines.append(
                f"- [{item.get('queue_type')}] `{item.get('action')}` "
                f"on `{item.get('target_page')}` risk={item.get('risk_level')}: {item.get('reason')}"
            )

    refresh_queue = as_list(record.get("refresh_queue"))
    governance_queue = as_list(record.get("governance_queue"))
    if refresh_queue or governance_queue:
        lines.extend(["", "## Governance Queues", ""])
        if refresh_queue:
            lines.append("- refresh_queue:")
            for item in refresh_queue:
                lines.append(f"  - `{item.get('target_page')}` {item.get('action')}: {item.get('reason')}")
        if governance_queue:
            lines.append("- high_impact_queue:")
            for item in governance_queue:
                lines.append(f"  - `{item.get('target_page')}` {item.get('action')}: {item.get('expected_effect')}")

    deferred_retries = as_list(record.get("deferred_retries"))
    if deferred_retries:
        lines.extend(["", "## Deferred Retries", ""])
        for item in deferred_retries:
            lines.append(
                f"- round {item.get('round')}: pages={format_list(as_list(item.get('retry_pages')))} "
                f"candidates={item.get('candidate_count', 0)} decisions={item.get('review_decisions', 0)} "
                f"applied={item.get('applied_operations', 0)} written={item.get('written_pages', 0)} "
                f"queued={item.get('queued_actions', 0)}"
            )

    lines.extend(["", "## Execution", ""])
    applied = as_list(record.get("applied_operations"))
    written_pages = as_list(record.get("written_pages"))
    written_page_details = as_list(record.get("written_page_details"))
    if not applied and not written_pages:
        lines.append("- No reviewed changes applied.")
    if operation_summary:
        lines.append(f"- success_rate: {fmt_number(operation_summary.get('success_rate'))}")
        lines.append(f"- failed_verifications: {operation_summary.get('failed_verifications', 0)}")
    for operation in applied:
        lines.append(f"- operation `{operation.get('action')}` on `{operation.get('target_page')}`: {operation.get('status')}")
    for page in written_pages:
        lines.append(f"- wrote `{page}`")
    applied_with_diff = [item for item in applied if as_dict(item).get("output_page") and as_dict(as_dict(item).get("details")).get("diff")]
    if applied_with_diff:
        lines.extend(["", "## Page Changes", ""])
        for item in applied_with_diff:
            operation = as_dict(item)
            details = as_dict(operation.get("details"))
            lines.append(
                f"- `{operation.get('output_page')}` action={operation.get('action')} "
                f"sections={format_list(as_list(details.get('patched_sections')))}"
            )
            diff = str(details.get("diff") or "")
            if diff:
                lines.extend(["", "```diff", diff, "```", ""])
            if details.get("diff_truncated"):
                lines.append("- diff_truncated: True")
    if written_page_details:
        if not applied_with_diff:
            lines.extend(["", "## Page Changes", ""])
        for item in written_page_details:
            details = as_dict(item)
            write_details = as_dict(details.get("write_details"))
            lines.append(
                f"- `{details.get('path')}` action={details.get('write_action')} "
                f"sections={format_list(as_list(write_details.get('patched_sections')))}"
            )
            diff = str(write_details.get("diff") or "")
            if diff:
                lines.extend(["", "```diff", diff, "```", ""])
            if write_details.get("diff_truncated"):
                lines.append("- diff_truncated: True")

    verifications = as_list(record.get("verifications"))
    if verifications:
        lines.extend(["", "## Post-fix Verification", ""])
        for verification in verifications:
            lines.append(
                f"- [{verification.get('status')}] `{verification.get('action')}` "
                f"on `{verification.get('target_page')}`: {verification.get('reason')}"
            )

    if rescan:
        lines.extend(["", "## Rescan", ""])
        rescan_issues = as_list(rescan.get("issues"))
        if not rescan_issues:
            lines.append("- No rescan issues.")
        else:
            for issue in rescan_issues[:50]:
                lines.append(f"- [{issue.get('severity')}] `{issue.get('code')}` in `{issue.get('path')}`: {issue.get('message')}")

    warnings = as_list(record.get("warnings"))
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)

    return "\n".join(lines).rstrip() + "\n"


def _semantic_candidates_record(payload: dict[str, Any]) -> dict[str, object] | None:
    if not payload:
        return None
    candidates = as_list(payload.get("candidates"))
    page_reviews = as_list(payload.get("page_reviews"))
    return {
        "schema_version": payload.get("schema_version"),
        "candidate_count": len(candidates),
        "page_review_count": len(page_reviews),
        "summary": payload.get("summary"),
        "warnings": as_list(payload.get("warnings")),
        "candidates": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "source": candidate.get("source"),
                "target_page": candidate.get("target_page"),
                "issue_type": candidate.get("issue_type"),
                "severity": candidate.get("severity"),
                "confidence": candidate.get("confidence"),
                "risk_hint": candidate.get("risk_hint"),
                "executor_hint": candidate.get("executor_hint"),
                "recommended_action": as_dict(candidate.get("recommended_action")).get("action"),
                "expected_effect": candidate.get("expected_effect"),
            }
            for candidate in candidates
            if isinstance(candidate, dict)
        ],
        "page_reviews": [
            {
                "path": review.get("path"),
                "verdict": review.get("verdict"),
                "overall_score": review.get("overall_score"),
            }
            for review in page_reviews
            if isinstance(review, dict)
        ],
    }


def _review_record(payload: dict[str, Any]) -> dict[str, object] | None:
    if not payload:
        return None
    decisions = as_list(payload.get("decisions"))
    return {
        "schema_version": payload.get("schema_version"),
        "decision_count": len(decisions),
        "summary": payload.get("summary"),
        "warnings": as_list(payload.get("warnings")),
        "decisions": [
            {
                "operation_index": decision.get("operation_index"),
                "decision": decision.get("decision"),
                "necessity": decision.get("necessity"),
                "correctness": decision.get("correctness"),
                "completeness": decision.get("completeness"),
                "executor_fit": decision.get("executor_fit"),
                "risk_level": decision.get("risk_level"),
                "confidence": decision.get("confidence"),
                "reason": decision.get("reason"),
            }
            for decision in decisions
            if isinstance(decision, dict)
        ],
    }


def _verification_summary(verifications: list[dict[str, Any]]) -> dict[str, object]:
    counts = {"verified": 0, "failed": 0, "skipped": 0}
    for verification in verifications:
        status = str(verification.get("status") or "")
        if status in counts:
            counts[status] += 1
    return {
        "total": len(verifications),
        **counts,
        "follow_up_required": counts["failed"] > 0,
    }


def _issue_summary(before: list[Any], after: list[Any] | None) -> dict[str, object]:
    before_counts = _issue_code_counts(before)
    after_counts = _issue_code_counts(after or [])
    return {
        "before_issue_count": len(before),
        "after_issue_count": len(after) if after is not None else None,
        "issue_delta": (len(after) - len(before)) if after is not None else None,
        "before_code_counts": before_counts,
        "after_code_counts": after_counts,
        "remaining_codes": sorted(after_counts),
    }


def _issue_code_counts(issues: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        code = str(getattr(issue, "code", "") or "")
        if code:
            counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def _quality_review_summary(payload: dict[str, Any]) -> dict[str, object]:
    reviews = [review for review in as_list(payload.get("page_reviews")) if isinstance(review, dict)]
    scores = [float(review.get("overall_score")) for review in reviews if isinstance(review.get("overall_score"), (int, float))]
    low_score_pages = [
        str(review.get("path"))
        for review in reviews
        if isinstance(review.get("overall_score"), (int, float)) and float(review.get("overall_score")) < 0.7
    ]
    return {
        "page_review_count": len(reviews),
        "average_overall_score": round(sum(scores) / len(scores), 3) if scores else None,
        "low_score_pages": low_score_pages,
    }


def _operation_summary(
    applied_operations: list[dict[str, Any]],
    written_pages: list[str],
    verifications: list[dict[str, Any]],
) -> dict[str, object]:
    verification_summary = _verification_summary(verifications)
    total_effects = len(applied_operations) + len(written_pages)
    failed = int(verification_summary.get("failed", 0))
    success_rate = None if total_effects == 0 else round((total_effects - failed) / total_effects, 3)
    return {
        "total_effects": total_effects,
        "success_rate": success_rate,
        "failed_verifications": failed,
    }


def _queue_by_type(actions: list[dict[str, Any]], queue_type: str) -> list[dict[str, Any]]:
    return [action for action in actions if action.get("queue_type") == queue_type]


def _governance_queue(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    high_impact_actions = {
        "queue_merge_candidate",
        "merge_pages",
        "split_page",
        "queue_conflict_review",
        "queue_graph_review",
    }
    return [
        action
        for action in actions
        if action.get("queue_type") == "report_only" and action.get("action") in high_impact_actions
    ]


def _trend_summary(previous_records: list[dict[str, object]], current_issue_summary: dict[str, object]) -> dict[str, object]:
    previous = previous_records[-1] if previous_records else {}
    previous_issue_summary = as_dict(previous.get("issue_summary"))
    previous_issue_count = previous_issue_summary.get("before_issue_count")
    current_issue_count = current_issue_summary.get("before_issue_count", 0)
    previous_counts = as_dict(previous_issue_summary.get("before_code_counts"))
    current_counts = as_dict(current_issue_summary.get("before_code_counts"))
    persistent_codes = {
        code: int(current_counts.get(code, 0))
        for code in sorted(current_counts)
        if code in previous_counts
    }
    return {
        "previous_runs_considered": len(previous_records),
        "previous_run_id": previous.get("run_id"),
        "previous_issue_count": previous_issue_count,
        "current_issue_count": current_issue_count,
        "issue_delta_from_previous": (int(current_issue_count) - int(previous_issue_count))
        if isinstance(current_issue_count, int) and isinstance(previous_issue_count, int)
        else None,
        "persistent_issue_codes": persistent_codes,
    }


def _issue_record(issue: Any) -> dict[str, object]:
    return {
        "code": issue.code,
        "severity": issue.severity,
        "path": issue.path,
        "message": issue.message,
        "details": issue.details,
    }


def _format_issue_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{code}={count}" for code, count in sorted(counts.items()))


def _format_hub_pages(items: list[Any]) -> str:
    if not items:
        return "none"
    parts = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        parts.append(f"{item.get('path')}({item.get('degree')})")
    return ", ".join(parts) if parts else "none"
