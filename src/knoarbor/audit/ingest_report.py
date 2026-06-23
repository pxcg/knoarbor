from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.audit.reports import write_maintenance_report
from knoarbor.audit.report_formatting import as_dict, as_list, cache_metric_lines, fmt_number, format_list, semantic_token_report_lines
from knoarbor.audit.token_ledger import append_ingest_token_records
from knoarbor.storage.ledger import append_jsonl_ledger, read_jsonl_ledger
from knoarbor.storage.wiki_index import relative_wiki_path


INGEST_LEDGER_PATH = "maintenance/ingest_ledger.jsonl"


def write_ingest_run_artifacts(
    vault_path: Path,
    result: Any,
    *,
    started_at: str,
    finished_at: str,
    run_id: str | None = None,
    append_ledger: bool = True,
    write_report: bool = True,
) -> tuple[str | None, str | None]:
    """Write compact ingest run report and append-only ledger entry."""

    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    record = build_ingest_run_record(result, run_id=run_id, started_at=started_at, finished_at=finished_at)
    record["quality_trend"] = build_source_quality_trend(record, read_jsonl_ledger(vault_path, INGEST_LEDGER_PATH, limit=100))
    ledger_path = append_jsonl_ledger(vault_path, INGEST_LEDGER_PATH, record) if append_ledger else None
    if append_ledger:
        append_ingest_token_records(vault_path, record)
    report_path = (
        write_maintenance_report(vault_path, "ingest", render_ingest_report(record), f"maintenance/ingest_report_{run_id}.md")
        if write_report
        else None
    )
    return (
        relative_wiki_path(vault_path, ledger_path) if ledger_path else None,
        relative_wiki_path(vault_path, report_path) if report_path else None,
    )


def build_ingest_run_record(result: Any, *, run_id: str, started_at: str, finished_at: str) -> dict[str, object]:
    return {
        "schema_version": "ingest_run.v1",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "stats": dict(result.stats),
        "metrics": dict(getattr(result, "metrics", {}) or {}),
        "document_processing": getattr(result, "document_processing", {}).model_dump()
        if hasattr(getattr(result, "document_processing", None), "model_dump")
        else dict(getattr(result, "document_processing", {}) or {}),
        "sources": [_source_record(source_result) for source_result in result.results],
        "lifecycle_candidates": [candidate.model_dump() for candidate in getattr(result, "lifecycle_candidates", [])],
    }


def render_ingest_report(record: dict[str, object]) -> str:
    stats = as_dict(record.get("stats"))
    metrics = as_dict(record.get("metrics"))
    semantic_metrics = as_dict(metrics.get("semantic"))
    sources = as_list(record.get("sources"))
    document_processing = as_dict(record.get("document_processing"))
    document_processing_stats = as_dict(document_processing.get("stats"))
    document_processing_items = as_list(document_processing.get("items"))
    lifecycle_candidates = as_list(record.get("lifecycle_candidates"))
    quality_trend = as_dict(record.get("quality_trend"))
    lines = [
        "# Ingest Report",
        "",
        f"- run_id: {record.get('run_id')}",
        f"- started_at: {record.get('started_at')}",
        f"- finished_at: {record.get('finished_at')}",
        f"- sources: {stats.get('source_count', 0)}",
        f"- processed: {stats.get('processed_count', 0)}",
        f"- skipped: {stats.get('skipped_count', 0)}",
        f"- failed: {stats.get('failed_count', 0)}",
        f"- written_pages: {stats.get('written_count', 0)}",
        f"- segments: {stats.get('segment_count', 0)} total, {stats.get('failed_segment_count', 0)} failed, max {stats.get('max_segment_chars', 0)} chars",
        f"- document_processing: {document_processing_stats.get('processed_count', 0)} processed, {document_processing_stats.get('failed_count', 0)} failed",
        f"- elapsed_seconds: {fmt_number(metrics.get('elapsed_seconds'))}",
        f"- semantic_calls: {semantic_metrics.get('semantic_call_count', 0)}",
        f"- total_tokens: {semantic_metrics.get('total_tokens', 0)}",
        *cache_metric_lines(semantic_metrics),
        f"- tokens_per_second: {fmt_number(semantic_metrics.get('tokens_per_second'))}",
        f"- lifecycle_candidates: {len(lifecycle_candidates)}",
        f"- recovery_candidates: {stats.get('recovery_candidate_count', 0)}",
        f"- source_concurrency: {stats.get('effective_max_concurrent_sources', 1)} effective / {stats.get('configured_max_concurrent_sources', 1)} configured",
        f"- execution_ledger: {metrics.get('execution_ledger_path', 'n/a')}",
        f"- repeated_failed_sources: {quality_trend.get('repeated_failed_sources', 0)}",
        f"- repeated_skipped_sources: {quality_trend.get('repeated_skipped_sources', 0)}",
        "",
        *semantic_token_report_lines(semantic_metrics),
        "## Run Summary",
        "",
        f"- source_status: {_status_summary(sources, 'status')}",
        f"- segment_status: {_segment_status_summary(sources)}",
        f"- write_summary: {stats.get('written_count', 0)} page(s) written across {_sources_with_writes(sources)} source(s)",
        f"- failure_summary: {_failure_summary(sources)}",
        f"- recovery_summary: {_recovery_summary(sources)}",
        "",
        "## Sources",
        "",
    ]
    if document_processing_items:
        lines.extend(["## Document Processing", ""])
        for item in document_processing_items:
            item_dict = as_dict(item)
            lines.append(
                f"- `{item_dict.get('adapter')}` `{item_dict.get('status')}` "
                f"{item_dict.get('input_path')} -> {item_dict.get('output_path') or 'no markdown'}"
            )
            if item_dict.get("error_message"):
                lines.append(f"  - error: {item_dict.get('error_type')}: {item_dict.get('error_message')}")
        lines.extend(["", "## Sources", ""])
    if not sources:
        lines.append("- No sources discovered.")
    for source in sources:
        generated_pages = as_list(source.get("generated_pages"))
        page_plan_operations = as_list(source.get("page_plan_operations"))
        redaction = as_dict(source.get("redaction"))
        context = as_dict(source.get("context"))
        quality_gate = as_dict(source.get("quality_gate"))
        checkpoint = as_dict(source.get("checkpoint"))
        source_metrics = as_dict(source.get("metrics"))
        source_semantic = as_dict(source_metrics.get("semantic"))
        segmentation = as_dict(source.get("segmentation"))
        segments = as_list(source.get("segments"))
        scoped_lint_result = as_dict(source.get("scoped_lint_result"))
        deterministic_lint = _scoped_deterministic_lint(scoped_lint_result)
        scoped_lint_stats = as_dict(deterministic_lint.get("stats"))
        policy_decision = as_dict(scoped_lint_result.get("policy_decision"))
        retrieval = as_dict(context.get("retrieval"))
        context_strategy_lines = _context_strategy_lines(context)
        touched_pages = as_list(source.get("touched_pages"))
        lines.extend(
            [
                f"### {source.get('source_file')}",
                "",
                f"- connector: {source.get('connector')}",
                f"- source_id: {source.get('source_id')}",
                f"- mode: {source.get('mode')}",
                f"- status: {source.get('status')}",
                f"- checkpoint_type: {checkpoint.get('checkpoint_type', 'source')}",
                f"- should_process: {source.get('should_process')}",
                f"- wrote: {source.get('wrote')}",
                f"- reason: {source.get('reason')}",
                f"- semantic_skip_reason: {source.get('semantic_skip_reason') or 'n/a'}",
                f"- redacted_count: {redaction.get('redacted_count', 0)}",
                f"- candidate_count: {retrieval.get('candidate_count', 0)}",
                f"- quality_gate_passed: {quality_gate.get('passed')}",
                f"- touched_pages: {len(touched_pages)}",
                f"- scoped_lint_issues: {scoped_lint_stats.get('issue_count', 'not_run')}",
                f"- maintenance_policy: {policy_decision.get('recommended_mode', 'not_run')}",
                f"- maintenance_policy_triggered: {policy_decision.get('triggered', False)}",
                f"- elapsed_seconds: {fmt_number(source_metrics.get('elapsed_seconds'))}",
                f"- semantic_calls: {source_semantic.get('semantic_call_count', 0)}",
                f"- total_tokens: {source_semantic.get('total_tokens', 0)}",
                *[f"- {line[2:]}" for line in cache_metric_lines(source_semantic)],
                f"- tokens_per_second: {fmt_number(source_semantic.get('tokens_per_second'))}",
                f"- approved_operations: {source.get('approved_operation_indexes', [])}",
                f"- segmentation: {segmentation.get('mode', 'none')} / {segmentation.get('segment_count', 0)} segment(s)",
                f"- segment_status: {_status_summary(segments, 'status') if segments else 'n/a'}",
                *context_strategy_lines,
                "",
                "Page plan operations:",
            ]
        )
        if source.get("status") == "failed":
            lines.extend(
                [
                    f"- error_stage: {source.get('error_stage')}",
                    f"- error_code: {source.get('error_code')}",
                    f"- error_category: {source.get('error_category')}",
                    f"- error_retryable: {source.get('error_retryable')}",
                    f"- error_hint: {source.get('error_hint')}",
                    f"- error_type: {source.get('error_type')}",
                    f"- error_message: {source.get('error_message')}",
                    "",
                ]
            )
        if page_plan_operations:
            for operation in page_plan_operations:
                lines.append(
                    f"- `{operation.get('action')}` `{operation.get('page_dir')}` "
                    f"{operation.get('title')} -> {operation.get('target_page') or 'new page'}"
                )
        else:
            lines.append("- None.")
        draft_atom_traces = as_list(source.get("draft_atom_traces"))
        if draft_atom_traces:
            lines.extend(["", "Draft atom traces:"])
            for trace in draft_atom_traces:
                trace = as_dict(trace)
                atom_ids = format_list(as_list(trace.get("atom_ids")))
                source_digest_ids = format_list(as_list(trace.get("source_digest_ids")))
                lines.append(
                    f"- operation {trace.get('operation_index')}: `{trace.get('page_dir')}` "
                    f"{trace.get('title')} / atoms={atom_ids} / source_digests={source_digest_ids}"
                )
        if segments:
            lines.extend(["", "Segments:"])
            for segment in segments:
                segment = as_dict(segment)
                segment_metrics = as_dict(as_dict(segment.get("metrics")).get("semantic"))
                lines.append(
                    f"- [{segment.get('index')}] {segment.get('title')} / "
                    f"{segment.get('chars')} chars / status: {segment.get('status')} / "
                    f"semantic_calls: {segment_metrics.get('semantic_call_count', 0)} / "
                    f"tokens: {segment_metrics.get('total_tokens', 0)} / "
                    f"cached: {segment_metrics.get('prompt_cached_tokens', 0)} / "
                    f"elapsed: {fmt_number(as_dict(segment.get('metrics')).get('elapsed_seconds'))}s"
                )
                if segment.get("error_message"):
                    lines.append(
                        f"  - error: {segment.get('error_stage') or 'segment'} / "
                        f"{segment.get('error_code') or segment.get('error_type')}: {segment.get('error_message')}"
                    )
                segment_operations = as_list(segment.get("page_plan_operations"))
                if segment_operations:
                    for operation in segment_operations:
                        lines.append(
                            f"  - `{operation.get('action')}` `{operation.get('page_dir')}` "
                            f"{operation.get('title')} -> {operation.get('target_page') or 'new page'}"
                        )
                segment_pages = as_list(segment.get("generated_pages"))
                if segment_pages:
                    lines.append(f"  - written_pages: {', '.join(str(page) for page in segment_pages)}")
                written_page_details = as_list(segment.get("written_page_details"))
                if written_page_details:
                    for item in written_page_details:
                        item_dict = as_dict(item)
                        write_details = as_dict(item_dict.get("write_details"))
                        sections = format_list(as_list(write_details.get("patched_sections")))
                        lines.append(
                            f"  - page_change: `{item_dict.get('path')}` action={item_dict.get('write_action')} "
                            f"sections={sections}"
                        )
                        diff = str(write_details.get("diff") or "")
                        if diff:
                            lines.extend(["", "```diff", diff, "```", ""])
                        if write_details.get("diff_truncated"):
                            lines.append("  - diff_truncated: True")
                segment_warnings = as_list(segment.get("warnings"))
                if segment_warnings:
                    lines.append(f"  - warnings: {'; '.join(str(warning) for warning in segment_warnings)}")
        lines.extend(["", "Generated pages:"])
        if generated_pages:
            lines.extend(f"- {page}" for page in generated_pages)
        else:
            lines.append("- None.")
        if touched_pages:
            lines.extend(["", "Scoped lint pages:"])
            lines.extend(f"- {page}" for page in touched_pages)
        scoped_lint_issues = as_list(deterministic_lint.get("issues"))
        scoped_lint_fixes = as_list(deterministic_lint.get("fixes"))
        trigger_reasons = as_list(policy_decision.get("trigger_reasons"))
        if scoped_lint_result:
            lines.extend(["", "Scoped lint result:"])
            if scoped_lint_result.get("error_type"):
                if scoped_lint_result.get("error_code"):
                    lines.append(f"- error_code: {scoped_lint_result.get('error_code')}")
                    lines.append(f"- error_category: {scoped_lint_result.get('error_category')}")
                    lines.append(f"- error_retryable: {scoped_lint_result.get('error_retryable')}")
                    lines.append(f"- error_hint: {scoped_lint_result.get('error_hint')}")
                lines.append(f"- error_type: {scoped_lint_result.get('error_type')}")
                lines.append(f"- error_message: {scoped_lint_result.get('error_message')}")
            elif scoped_lint_issues:
                for issue in scoped_lint_issues:
                    lines.append(f"- [{issue.get('severity')}] `{issue.get('code')}` in `{issue.get('path')}`: {issue.get('message')}")
            else:
                lines.append("- No scoped lint issues found.")
            if scoped_lint_fixes:
                lines.extend(["", "Scoped lint fixes:"])
                for fix in scoped_lint_fixes:
                    lines.append(f"- [{fix.get('mode')}] `{fix.get('action')}` for `{fix.get('path')}`: {fix.get('description')}")
            if trigger_reasons:
                lines.extend(["", "Maintenance policy reasons:"])
                lines.extend(f"- {reason}" for reason in trigger_reasons)
        warnings = as_list(source.get("warnings"))
        if warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    lines.extend(["## Source Lifecycle Candidates", ""])
    if not lifecycle_candidates:
        lines.append("- None.")
    else:
        for candidate in lifecycle_candidates:
            action = as_dict(candidate.get("recommended_action"))
            lines.append(
                f"- `{candidate.get('issue_type')}` `{candidate.get('target_page')}` "
                f"via `{action.get('action')}`: {candidate.get('expected_effect')}"
            )
    lines.extend(["", "## Recovery Candidates", ""])
    recovery_sources = [source for source in sources if _is_recovery_candidate(source)]
    if not recovery_sources:
        lines.append("- None.")
    else:
        for source in recovery_sources:
            source_dict = as_dict(source)
            lines.append(
                f"- `{source_dict.get('source_file')}` via `{source_dict.get('connector')}`: "
                f"{source_dict.get('error_code') or source_dict.get('error_type')} / "
                f"{source_dict.get('error_hint') or source_dict.get('error_message')}"
            )
    return "\n".join(lines).rstrip() + "\n"


def build_source_quality_trend(record: dict[str, object], previous_records: list[dict[str, object]]) -> dict[str, object]:
    previous_by_source = _previous_source_history(previous_records)
    repeated_failed = 0
    repeated_skipped = 0
    source_trends: list[dict[str, object]] = []
    for source in as_list(record.get("sources")):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "")
        history = previous_by_source.get(source_id, [])
        previous_failed = sum(1 for item in history if item.get("status") == "failed")
        previous_skipped = sum(1 for item in history if item.get("status") == "skipped")
        if source.get("status") == "failed" and previous_failed:
            repeated_failed += 1
        if source.get("status") == "skipped" and previous_skipped:
            repeated_skipped += 1
        source_trends.append(
            {
                "source_id": source_id,
                "previous_runs": len(history),
                "previous_failed_count": previous_failed,
                "previous_skipped_count": previous_skipped,
                "current_status": source.get("status"),
                "current_quality_gate_passed": as_dict(source.get("quality_gate")).get("passed"),
                "current_semantic_skip_reason": source.get("semantic_skip_reason"),
            }
        )
    return {
        "window": len(previous_records),
        "repeated_failed_sources": repeated_failed,
        "repeated_skipped_sources": repeated_skipped,
        "sources": source_trends,
    }


def _previous_source_history(records: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    history: dict[str, list[dict[str, object]]] = {}
    for record in records:
        for source in as_list(record.get("sources")):
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_id")
            if isinstance(source_id, str) and source_id:
                history.setdefault(source_id, []).append(source)
    return history


def _status_summary(items: list[object], key: str) -> str:
    counts: dict[str, int] = {}
    for item in items:
        item_dict = as_dict(item)
        value = str(item_dict.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return "none"
    return ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))


def _segment_status_summary(sources: list[object]) -> str:
    segments = [
        segment
        for source in sources
        for segment in as_list(as_dict(source).get("segments"))
    ]
    return _status_summary(segments, "status") if segments else "none"


def _sources_with_writes(sources: list[object]) -> int:
    return sum(1 for source in sources if as_list(as_dict(source).get("generated_pages")))


def _failure_summary(sources: list[object]) -> str:
    failures: list[str] = []
    for source in sources:
        source_dict = as_dict(source)
        if source_dict.get("status") == "failed":
            failures.append(f"{source_dict.get('source_file')}: {source_dict.get('error_code') or source_dict.get('error_type') or 'Error'}")
        for segment in as_list(source_dict.get("segments")):
            segment_dict = as_dict(segment)
            if segment_dict.get("status") == "failed":
                failures.append(
                    f"{source_dict.get('source_file')} segment {segment_dict.get('index')}: "
                    f"{segment_dict.get('error_code') or segment_dict.get('error_type') or 'Error'}"
                )
    return "; ".join(failures) if failures else "none"


def _recovery_summary(sources: list[object]) -> str:
    candidates = [source for source in sources if _is_recovery_candidate(source)]
    if not candidates:
        return "none"
    return ", ".join(str(as_dict(source).get("source_file") or as_dict(source).get("source_id")) for source in candidates)


def _is_recovery_candidate(source: object) -> bool:
    source_dict = as_dict(source)
    if source_dict.get("status") != "failed":
        return False
    if bool(source_dict.get("error_retryable")):
        return True
    return any(bool(as_dict(segment).get("error_retryable")) for segment in as_list(source_dict.get("segments")))


def _source_record(source_result: Any) -> dict[str, object]:
    semantic_result = source_result.semantic_result
    return {
        "connector": source_result.connector,
        "source_id": source_result.source_id,
        "source_file": source_result.source_file,
        "should_process": source_result.should_process,
        "mode": source_result.mode,
        "reason": source_result.reason,
        "status": source_result.status,
        "error_stage": source_result.error_stage,
        "error_code": source_result.error_code,
        "error_category": source_result.error_category,
        "error_retryable": source_result.error_retryable,
        "error_hint": source_result.error_hint,
        "error_type": source_result.error_type,
        "error_message": source_result.error_message,
        "redaction": dict(source_result.redaction),
        "context": dict(source_result.context),
        "quality_gate": dict(source_result.quality_gate),
        "checkpoint": dict(source_result.checkpoint),
        "touched_pages": list(source_result.touched_pages),
        "scoped_lint": dict(source_result.scoped_lint),
        "scoped_lint_result": dict(source_result.scoped_lint_result),
        "approved_operation_indexes": list(source_result.approved_operation_indexes),
        "generated_pages": list(source_result.generated_pages),
        "wrote": source_result.wrote,
        "semantic_skip_reason": source_result.semantic_skip_reason,
        "metrics": dict(source_result.metrics),
        "segmentation": dict(getattr(source_result, "segmentation", {}) or {}),
        "segments": list(getattr(source_result, "segments", []) or []),
        "page_plan_operations": _page_plan_operations(semantic_result),
        "draft_atom_traces": _draft_atom_traces(semantic_result),
        "review_decisions": _review_decisions(semantic_result),
        "semantic_stage_warnings": _semantic_stage_warnings(semantic_result),
        "warnings": _final_warnings(source_result, semantic_result),
    }


def _context_strategy_lines(context: dict[str, Any]) -> list[str]:
    retrieval = as_dict(context.get("retrieval"))
    retrieval_stats = as_dict(retrieval.get("stats"))
    source_digest = as_dict(context.get("source_digest"))
    source_digest_summary = as_dict(source_digest.get("summary"))
    knowledge_atoms = as_dict(context.get("knowledge_atoms"))
    knowledge_atom_index_path = context.get("knowledge_atom_index_path")
    knowledge_atom_quality = as_dict(context.get("knowledge_atom_quality"))
    materialized = as_dict(context.get("materialized_pages"))
    compile_context = as_dict(context.get("compile_context"))
    lines: list[str] = []
    if retrieval_stats or source_digest_summary or knowledge_atoms or materialized or compile_context:
        lines.append(f"- page_plan_context_policy: {retrieval_stats.get('page_plan_context_policy', 'n/a')}")
        lines.append(f"- page_plan_profile_chars: {retrieval_stats.get('page_plan_profile_chars', 'n/a')}")
        if source_digest_summary:
            lines.append(
                "- source_digest: "
                f"id={source_digest.get('digest_id', 'n/a')}, "
                f"units={source_digest_summary.get('units', 0)}, "
                f"observations={source_digest_summary.get('observations', 0)}, "
                f"evidence_spans={source_digest_summary.get('evidence_spans', 0)}"
            )
        if knowledge_atoms:
            lines.append(
                "- knowledge_atoms: "
                f"entities={knowledge_atoms.get('entities', 0)}, "
                f"claims={knowledge_atoms.get('claims', 0)}, "
                f"relations={knowledge_atoms.get('relations', 0)}, "
                f"evidence_spans={knowledge_atoms.get('evidence_spans', 0)}, "
                f"unsupported={knowledge_atoms.get('unsupported', 0)}, "
                f"conflicting={knowledge_atoms.get('conflicting', 0)}, "
                f"rejected={knowledge_atoms.get('rejected', 0)}"
            )
        if knowledge_atom_index_path:
            lines.append(f"- knowledge_atom_index: {knowledge_atom_index_path}")
        quality_issues = knowledge_atom_quality.get("issues")
        if isinstance(quality_issues, list) and quality_issues:
            lines.append(f"- knowledge_atom_quality_issues: {len(quality_issues)}")
        lines.append(f"- materialized_context_policy: {materialized.get('context_policy', 'n/a')}")
        lines.append(f"- materialized_context_chars: {materialized.get('materialized_context_chars', 'n/a')}")
        lines.append(
            "- compile_context_pages: "
            f"targets={compile_context.get('target_pages', 'n/a')}, "
            f"related={compile_context.get('related_pages', 'n/a')}, "
            f"candidates={compile_context.get('candidate_pages', 'n/a')}"
        )
    return lines


def _page_plan_operations(semantic_result: Any | None) -> list[dict[str, object]]:
    if semantic_result is None:
        return []
    operations = []
    for index, operation in enumerate(semantic_result.wiki_page_plan.operations):
        operations.append(
            {
                "operation_index": index,
                "action": operation.action,
                "target_page": operation.target_page,
                "page_dir": operation.page_dir,
                "canonical_path": operation.canonical_path,
                "legacy_paths": list(operation.legacy_paths),
                "title": operation.title,
                "knowledge_object": operation.knowledge_object,
                "selected_claim_ids": list(operation.selected_claim_ids),
                "selected_relation_ids": list(operation.selected_relation_ids),
                "source_digest_ids": list(operation.source_digest_ids),
                "decision_reason": operation.decision_reason,
            }
        )
    return operations


def _draft_atom_traces(semantic_result: Any | None) -> list[dict[str, object]]:
    if semantic_result is None:
        return []
    return [
        {
            "operation_index": draft.operation_index,
            "page_dir": draft.page_dir,
            "title": draft.title,
            "atom_ids": list(draft.atom_ids),
            "source_digest_ids": list(draft.source_digest_ids),
        }
        for draft in semantic_result.wiki_draft_batch.drafts
        if draft.atom_ids or draft.source_digest_ids
    ]


def _review_decisions(semantic_result: Any | None) -> list[dict[str, object]]:
    if semantic_result is None:
        return []
    return [
        {
            "operation_index": decision.operation_index,
            "decision": decision.decision,
            "quality_score": decision.quality_score,
            "risk_level": decision.risk_level,
            "write_safety": decision.write_safety,
            "reason": decision.reason,
        }
        for decision in semantic_result.ingest_draft_review.decisions
    ]


def _semantic_stage_warnings(semantic_result: Any | None) -> dict[str, list[str]]:
    if semantic_result is None:
        return {}
    return {
        "normalize": list(semantic_result.knowledge_extract.warnings),
        "page_plan": list(semantic_result.wiki_page_plan.warnings),
        "draft": list(semantic_result.wiki_draft_batch.warnings),
        "review": list(semantic_result.ingest_draft_review.warnings),
    }


def _final_warnings(source_result: Any, semantic_result: Any | None) -> list[str]:
    if semantic_result is None:
        return []
    stage_warnings = _semantic_stage_warnings(semantic_result)
    warnings = [
        *stage_warnings.get("normalize", []),
        *stage_warnings.get("page_plan", []),
    ]
    if not getattr(source_result, "wrote", False):
        warnings.extend(stage_warnings.get("draft", []))
        warnings.extend(stage_warnings.get("review", []))
    return _dedupe_strings(warnings)


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _scoped_deterministic_lint(scoped_lint_result: dict[str, Any]) -> dict[str, Any]:
    return as_dict(scoped_lint_result.get("deterministic_lint"))
