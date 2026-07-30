from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.audit.contracts import LEDGER_PATHS, LEDGER_SCHEMA_VERSIONS
from knoarbor.core.schemas.wiki_lint import LintRunResult
from knoarbor.audit.reports import write_maintenance_report
from knoarbor.audit.report_formatting import as_dict, as_list, cache_metric_lines, fmt_number, semantic_token_report_lines
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
    issue_summary = _issue_summary(
        deterministic.issues,
        result.post_repair_lint.issues if result.post_repair_lint is not None else None,
    )
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
        "repair_plan": result.repair_plan,
        "repair_results": result.repair_results,
        "metrics": dict(result.metrics),
        "warnings": result.warnings,
    }


def render_lint_run_report(record: dict[str, object]) -> str:
    deterministic = as_dict(record.get("deterministic_lint"))
    deterministic_stats = as_dict(deterministic.get("stats"))
    policy = as_dict(record.get("policy_decision"))
    semantic = as_dict(record.get("semantic_candidates"))
    review = as_dict(record.get("maintenance_review"))
    issue_summary = as_dict(record.get("issue_summary"))
    trend_summary = as_dict(record.get("trend_summary"))
    graph_health = as_dict(deterministic_stats.get("graph_health"))
    quality_review_summary = as_dict(record.get("quality_review_summary"))
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
        f"- repair_plan: {len(as_list(record.get('repair_plan')))}",
        f"- repair_results: {len(as_list(record.get('repair_results')))}",
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
        f"- before_repair: {issue_summary.get('before_issue_count', 0)}",
        f"- after_repair: {issue_summary.get('after_issue_count', 'not_run')}",
        f"- issue_delta: {issue_summary.get('issue_delta', 'n/a')}",
        f"- issue_codes: {_format_issue_counts(as_dict(issue_summary.get('before_code_counts')))}",
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

    lines.extend(["", "## Repair Plan", ""])
    repair_plan = as_list(record.get("repair_plan"))
    if not repair_plan:
        lines.append("- No repairs were planned.")
    else:
        for item in repair_plan:
            lines.append(
                f"- [{item.get('queue_type')}] `{item.get('action')}` "
                f"on `{item.get('target_page')}` risk={item.get('risk_level')}: {item.get('reason')}"
            )

    lines.extend(["", "## Repair Results", ""])
    repair_results = as_list(record.get("repair_results"))
    if not repair_results:
        lines.append("- No automatic repairs were required.")
    else:
        for item in repair_results:
            detail = f" error={item.get('error')}" if item.get("error") else ""
            lines.append(
                f"- [{item.get('status')}] `{item.get('action')}` by `{item.get('owner')}` "
                f"on `{item.get('target_page') or item.get('target')}`{detail}"
            )

    lines.extend(
        [
            "",
            "## Write Boundary",
            "",
            "- Repairs were executed only through ingest or materialization owner workflows.",
        ]
    )

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
