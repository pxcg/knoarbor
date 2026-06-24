from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import time

from typing import Callable

from knoarbor.connectors.selection import selected_connector_configs
from knoarbor.core.checkpoints import CheckpointStore
from knoarbor.core.config import IngestSegmentationConfig, KnoArborConfig, PrivacyConfig
from knoarbor.core.errors import error_info
from knoarbor.core.ignore import KnoArborIgnore
from knoarbor.core.redaction import redact_source_document
from knoarbor.core.schemas.ingest_pipeline import IngestPipelineResult, IngestSourceResult
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.document_processing import DocumentProcessingPipeline, DocumentProcessingResult
from knoarbor.audit.ingest_execution import write_ingest_execution_ledger
from knoarbor.audit.ingest_report import write_ingest_run_artifacts
from knoarbor.semantic.ingest_workflow import IngestSemanticWorkflow, IngestSemanticWorkflowResult
from knoarbor.semantic.metrics import empty_run_metrics, summarize_semantic_runs
from knoarbor.pipelines.ingest_context import IngestContextProvider
from knoarbor.pipelines.ingest_write_gate import IngestWriteGate
from knoarbor.pipelines.ingest_postprocess import (
    IngestPostProcessor,
    approved_write_items,
    scoped_lint_payload,
)
from knoarbor.pipelines.ingest_semantic import (
    IngestSemanticRunner,
    semantic_history_length,
    semantic_history_slice,
)
from knoarbor.pipelines.ingest_write_policy import IngestWritePolicy
from knoarbor.pipelines.ingest_checkpoint import (
    _checkpoint_payload,
    _commit_checkpoint_plan,
    _document_for_checkpoint,
    _prepare_checkpoint_plan,
    _should_commit_checkpoint_result,
)
from knoarbor.pipelines.ingest_aggregation import (
    SegmentSemanticArtifacts,
    aggregate_segment_semantic_artifacts,
)
from knoarbor.pipelines.ingest_lifecycle import relative_or_absolute, source_lifecycle_candidates
from knoarbor.pipelines.ingest_metrics import (
    combine_redactions,
    ingest_run_metrics,
    max_segment_chars,
    recovery_candidate_count,
    segment_count,
    segment_status_count,
    source_processed,
)
from knoarbor.pipelines.lint import WikiLintPipeline
from knoarbor.pipelines.source import SourcePipeline, SourcePipelineFailure, SourcePipelineItem
from knoarbor.pipelines.source_segmentation import SourceSegmentBatch, SourceSegmenter
from knoarbor.pipelines.write import WikiWritePipeline
from knoarbor.runtime import current_run_monitor, vault_write_lock
from knoarbor.storage.source_metrics import connector_source_metric_key, update_source_counts


class IngestSourceExecutor:
    """Executes one source document through semantic ingest, gate, and optional write."""

    def __init__(
        self,
        *,
        semantic_workflow: IngestSemanticWorkflow,
        write_pipeline: WikiWritePipeline,
        context_provider: IngestContextProvider,
        write_gate: IngestWriteGate,
        checkpoint_store: CheckpointStore,
        lint_pipeline: WikiLintPipeline | None = None,
        write_policy: IngestWritePolicy | None = None,
    ) -> None:
        self.semantic_workflow = semantic_workflow
        self.write_pipeline = write_pipeline
        self.context_provider = context_provider
        self.write_gate = write_gate
        self.checkpoint_store = checkpoint_store
        self.lint_pipeline = lint_pipeline or WikiLintPipeline()
        self.write_policy = write_policy or IngestWritePolicy()
        self.semantic_runner = IngestSemanticRunner(
            semantic_workflow=self.semantic_workflow,
            context_provider=self.context_provider,
        )
        self.post_processor = IngestPostProcessor(
            write_pipeline=self.write_pipeline,
            lint_pipeline=self.lint_pipeline,
            write_policy=self.write_policy,
            clear_context_cache=self.context_provider.clear_cache,
        )

    def run_item(
        self,
        *,
        connector_name: str,
        item: SourcePipelineItem,
        vault_path: Path,
        state: dict[str, object],
        checkpoint_path: Path,
        index_payload: dict[str, object],
        ignore: KnoArborIgnore,
        privacy_config: PrivacyConfig,
        write: bool,
        max_tokens: int | None,
        auto_scoped_lint: bool,
        auto_apply_safe_lint_fixes: bool,
        scoped_lint_include_related: bool,
        segmentation_config: IngestSegmentationConfig,
    ) -> IngestSourceResult:
        monitor = current_run_monitor()
        started = time.perf_counter()
        if monitor:
            monitor.event("source_started", stage="checkpoint", current_item=item.raw.source_id, message=f"Checking source {item.raw.source_id}.")
            monitor.raise_if_cancelled()
        checkpoint_plan = _prepare_checkpoint_plan(
            self.checkpoint_store,
            connector_name=connector_name,
            item=item,
            vault_path=vault_path,
            state=state,
        )
        if _is_ignored(ignore, vault_path, Path(item.raw.raw_path), checkpoint_plan["source_file"]):
            if monitor:
                monitor.event("source_ignored", stage="checkpoint", current_item=checkpoint_plan["source_id"], message="Source ignored by .knoarborignore.")
            result = IngestSourceResult(
                connector=connector_name,
                source_id=checkpoint_plan["source_id"],
                source_file=checkpoint_plan["source_file"],
                should_process=False,
                mode="ignored",
                reason="Source matched .knoarborignore.",
                status="ignored",
                checkpoint=_checkpoint_payload(checkpoint_plan),
            )
            result.metrics = empty_run_metrics(time.perf_counter() - started)
            return result

        result = IngestSourceResult(
            connector=connector_name,
            source_id=checkpoint_plan["source_id"],
            source_file=checkpoint_plan["source_file"],
            should_process=checkpoint_plan["should_process"],
            mode=checkpoint_plan["mode"],
            reason=checkpoint_plan["reason"],
            status="processed",
            checkpoint=_checkpoint_payload(checkpoint_plan),
        )
        if not checkpoint_plan["should_process"]:
            if monitor:
                monitor.event("source_skipped", stage="checkpoint", current_item=checkpoint_plan["source_id"], message=checkpoint_plan["reason"])
            result.status = "skipped"
            result.metrics = empty_run_metrics(time.perf_counter() - started)
            return result

        try:
            if monitor:
                monitor.event("source_processing", stage="segmentation", current_item=checkpoint_plan["source_id"], message="Preparing source segments.")
            document = _document_for_checkpoint(item.document, checkpoint_plan)
            result = self._run_document_segments(
                result,
                document=document,
                vault_path=vault_path,
                index_payload=index_payload,
                source_file=checkpoint_plan["source_file"],
                privacy_config=privacy_config,
                write=write,
                max_tokens=max_tokens,
                auto_scoped_lint=auto_scoped_lint,
                auto_apply_safe_lint_fixes=auto_apply_safe_lint_fixes,
                scoped_lint_include_related=scoped_lint_include_related,
                segmentation_config=segmentation_config,
            )
            if _should_commit_checkpoint_result(result, write=write):
                with vault_write_lock(vault_path):
                    _commit_checkpoint_plan(
                        self.checkpoint_store,
                        vault_path=vault_path,
                        state=state,
                        checkpoint_plan=checkpoint_plan,
                        generated_pages=result.generated_pages,
                        fallback_content_hash=item.raw.content_hash[:12],
                    )
                    self.checkpoint_store.write_state(vault_path, checkpoint_path, state)
            if monitor:
                monitor.event(
                    "source_finished",
                    stage="source_finished",
                    current_item=checkpoint_plan["source_id"],
                    message=f"Finished source with status {result.status}.",
                    payload={"generated_pages": result.generated_pages, "status": result.status},
                )
        except Exception as exc:
            _mark_failed_source(result, "source", exc)
            if monitor:
                monitor.event("source_failed", stage="source_failed", current_item=checkpoint_plan["source_id"], message=str(exc))
        result.metrics.setdefault("elapsed_seconds", time.perf_counter() - started)
        return result

    def run_document(
        self,
        document: SourceDocument,
        *,
        vault_path: Path,
        privacy_config: PrivacyConfig,
        write: bool,
        max_tokens: int | None,
        auto_scoped_lint: bool = True,
        auto_apply_safe_lint_fixes: bool = True,
        scoped_lint_include_related: bool = True,
        segmentation_config: IngestSegmentationConfig | None = None,
    ) -> IngestSourceResult:
        started = time.perf_counter()
        result = IngestSourceResult(
            connector=document.origin.connector,
            source_id=document.source_id,
            source_file=document.origin.raw_path,
            should_process=True,
            mode=document.checkpoint.mode,
            reason="Explicit source document input.",
        )
        try:
            result = self._run_document_segments(
                result,
                document=document,
                vault_path=vault_path,
                index_payload=_read_index_payload(vault_path),
                source_file=document.origin.raw_path,
                privacy_config=privacy_config,
                write=write,
                max_tokens=max_tokens,
                auto_scoped_lint=auto_scoped_lint,
                auto_apply_safe_lint_fixes=auto_apply_safe_lint_fixes,
                scoped_lint_include_related=scoped_lint_include_related,
                segmentation_config=segmentation_config or IngestSegmentationConfig(),
            )
            result.metrics.setdefault("elapsed_seconds", time.perf_counter() - started)
            return result
        except Exception as exc:
            _mark_failed_source(result, "source", exc)
            result.metrics = empty_run_metrics(time.perf_counter() - started)
            return result

    def _run_document_core(
        self,
        result: IngestSourceResult,
        *,
        document: SourceDocument,
        vault_path: Path,
        index_payload: dict[str, object],
        source_file: str,
        privacy_config: PrivacyConfig,
        write: bool,
        max_tokens: int | None,
        auto_scoped_lint: bool,
        auto_apply_safe_lint_fixes: bool,
        scoped_lint_include_related: bool,
    ) -> IngestSourceResult:
        started = time.perf_counter()
        redacted = redact_source_document(document, privacy_config)
        result.redaction = _redaction_payload(redacted.enabled, redacted.counts)
        history_start = semantic_history_length(self.semantic_workflow)
        try:
            semantic_run = self.semantic_runner.run(
                vault_path=vault_path,
                document=redacted.document,
                index_payload=index_payload,
                source_file=source_file,
                max_tokens=max_tokens,
            )
        except Exception:
            result.metrics = {
                "elapsed_seconds": time.perf_counter() - started,
                "semantic": summarize_semantic_runs(semantic_history_slice(self.semantic_workflow, history_start)),
            }
            raise
        semantic_result = semantic_run.semantic_result
        context_payload = semantic_run.context_payload
        candidate_page_context = semantic_run.candidate_page_context
        result.context = context_payload
        result.metrics = {
            "semantic": context_payload.get("semantic_metrics", summarize_semantic_runs([])),
        }
        approved_indexes = sorted(_approved_ingest_operation_indexes(semantic_result))
        gate_result = self.write_gate.validate(
            semantic_result,
            approved_indexes,
            candidate_page_context=candidate_page_context,
        )
        result.write_gate = gate_result.model_dump()
        approved_indexes = gate_result.approved_operation_indexes
        result.semantic_result = semantic_result
        result.approved_operation_indexes = approved_indexes
        result.semantic_skip_reason = _semantic_skip_reason(semantic_result)
        if result.semantic_skip_reason and not approved_indexes:
            result.status = "skipped"
        if not gate_result.passed:
            _mark_failed_source(result, "write_gate", ValueError(_write_gate_error_message(gate_result.model_dump())))

        if write and approved_indexes:
            self.post_processor.write_approved_items(
                vault_path=vault_path,
                result=result,
                items=approved_write_items(
                    semantic_result=semantic_result,
                    approved_indexes=approved_indexes,
                    source_file=source_file,
                    privacy_config=privacy_config,
                ),
                semantic_results=[semantic_result],
            )
        result.touched_pages = _touched_pages(result, candidate_page_context)
        result.scoped_lint = scoped_lint_payload(result)
        if write and auto_scoped_lint and result.touched_pages:
            self.post_processor.run_scoped_lint(
                result=result,
                vault_path=vault_path,
                apply_safe_fixes=auto_apply_safe_lint_fixes,
                include_related=scoped_lint_include_related,
            )
        result.metrics.setdefault("elapsed_seconds", time.perf_counter() - started)
        return result

    def _run_document_segments(
        self,
        result: IngestSourceResult,
        *,
        document: SourceDocument,
        vault_path: Path,
        index_payload: dict[str, object],
        source_file: str,
        privacy_config: PrivacyConfig,
        write: bool,
        max_tokens: int | None,
        auto_scoped_lint: bool,
        auto_apply_safe_lint_fixes: bool,
        scoped_lint_include_related: bool,
        segmentation_config: IngestSegmentationConfig,
    ) -> IngestSourceResult:
        started = time.perf_counter()
        monitor = current_run_monitor()
        batch = SourceSegmenter(segmentation_config).segment(document)
        result.segmentation = batch.summary()
        if monitor:
            monitor.event(
                "segments_created",
                stage="segmentation",
                current_item=result.source_id,
                message=f"Created {len(batch.segments)} segment(s).",
                progress={"total": len(batch.segments), "completed": 0, "current": result.source_id},
                payload=result.segmentation,
            )
            monitor.raise_if_cancelled()
        if len(batch.segments) == 1 and batch.segments[0].is_full_source:
            result = self._run_document_core(
                result,
                document=batch.segments[0].document,
                vault_path=vault_path,
                index_payload=index_payload,
                source_file=source_file,
                privacy_config=privacy_config,
                write=write,
                max_tokens=max_tokens,
                auto_scoped_lint=auto_scoped_lint,
                auto_apply_safe_lint_fixes=auto_apply_safe_lint_fixes,
                scoped_lint_include_related=scoped_lint_include_related,
            )
            result.segments = [_segment_record(batch, 0, result)]
            return result

        segment_results: list[IngestSourceResult] = []
        touched_pages: list[str] = []
        segment_artifacts: list[SegmentSemanticArtifacts] = []
        history_start = semantic_history_length(self.semantic_workflow)

        for segment in batch.segments:
            segment_started = time.perf_counter()
            if monitor:
                monitor.event(
                    "segment_started",
                    stage="segment_ingest",
                    current_item=segment.title,
                    message=f"Processing segment {segment.index + 1}/{len(batch.segments)}.",
                    progress={"total": len(batch.segments), "completed": segment.index, "current": segment.title},
                    payload={"segment_id": segment.segment_id, "chars": len(segment.content)},
                )
                monitor.raise_if_cancelled()
            segment_result = IngestSourceResult(
                connector=result.connector,
                source_id=result.source_id,
                source_file=source_file,
                should_process=True,
                mode=result.mode,
                reason=f"Segment {segment.index + 1}/{len(batch.segments)} of {result.reason}",
                checkpoint=dict(result.checkpoint),
            )
            segment_history_start = semantic_history_length(self.semantic_workflow)
            try:
                redacted = redact_source_document(segment.document, privacy_config)
                segment_result.redaction = _redaction_payload(redacted.enabled, redacted.counts)
                extraction = self.semantic_runner.extract_source(
                    document=redacted.document,
                    max_tokens=max_tokens,
                )
                segment_artifacts.append(
                    SegmentSemanticArtifacts(
                        knowledge_extract=extraction.knowledge_extract,
                        source_digest=extraction.source_digest,
                        knowledge_atom_batch=extraction.knowledge_atom_batch,
                    )
                )
                segment_result.context = {
                    **extraction.context_payload,
                    "segment_semantic_stage": "atom_extraction",
                }
                segment_result.metrics = {
                    "elapsed_seconds": time.perf_counter() - segment_started,
                    "semantic": summarize_semantic_runs(semantic_history_slice(self.semantic_workflow, segment_history_start)),
                }
            except Exception as exc:
                _mark_failed_source(segment_result, "segment", exc)
                segment_result.metrics.setdefault("elapsed_seconds", time.perf_counter() - segment_started)
            segment_results.append(segment_result)
            if monitor:
                monitor.event(
                    "segment_finished",
                    stage="segment_ingest",
                    current_item=segment.title,
                    message=f"Finished segment {segment.index + 1}/{len(batch.segments)} with status {segment_result.status}.",
                    progress={"total": len(batch.segments), "completed": segment.index + 1, "current": segment.title},
                    payload={"status": segment_result.status, "approved_operations": segment_result.approved_operation_indexes},
            )

        result.segments = [_segment_record(batch, index, segment_result) for index, segment_result in enumerate(segment_results)]
        result.redaction = combine_redactions([segment.redaction for segment in segment_results])
        failed_segments = [segment for segment in segment_results if segment.status == "failed"]
        if failed_segments:
            first = failed_segments[0]
            _copy_source_error(result, first, fallback_stage=first.error_stage or "segment")
            result.touched_pages = _dedupe_pages(touched_pages)
            result.scoped_lint = scoped_lint_payload(result)
            return result

        aggregate = aggregate_segment_semantic_artifacts(segment_artifacts)
        if monitor:
            monitor.event(
                "segment_aggregation_finished",
                stage="segment_aggregation",
                current_item=result.source_id,
                message=f"Aggregated {len(segment_artifacts)} segment semantic result(s) before page planning.",
                payload=aggregate.stats,
            )
            monitor.raise_if_cancelled()
        try:
            semantic_run = self.semantic_runner.plan_compile_review(
                vault_path=vault_path,
                knowledge_extract=aggregate.knowledge_extract,
                source_digest=aggregate.source_digest,
                knowledge_atom_batch=aggregate.knowledge_atom_batch,
                knowledge_atom_quality=aggregate.knowledge_atom_quality,
                index_payload=index_payload,
                source_file=source_file,
                max_tokens=max_tokens,
                history_start=history_start,
                extra_context={
                    "segment_aggregation": aggregate.stats,
                    "segment_semantic_strategy": "source_level_page_plan",
                },
            )
        except Exception as exc:
            _mark_failed_source(result, "source_level_semantic", exc)
            result.touched_pages = _dedupe_pages(touched_pages)
            result.scoped_lint = scoped_lint_payload(result)
            result.metrics = {
                "elapsed_seconds": time.perf_counter() - started,
                "semantic": summarize_semantic_runs(semantic_history_slice(self.semantic_workflow, history_start)),
            }
            return result

        semantic_result = semantic_run.semantic_result
        result.semantic_result = semantic_result
        result.context = semantic_run.context_payload
        result.metrics = {
            "elapsed_seconds": time.perf_counter() - started,
            "semantic": semantic_run.context_payload.get("semantic_metrics", summarize_semantic_runs([])),
        }
        approved_indexes = sorted(_approved_ingest_operation_indexes(semantic_result))
        gate_result = self.write_gate.validate(
            semantic_result,
            approved_indexes,
            candidate_page_context=semantic_run.candidate_page_context,
        )
        result.write_gate = gate_result.model_dump()
        approved_indexes = gate_result.approved_operation_indexes
        result.approved_operation_indexes = approved_indexes
        result.semantic_skip_reason = _semantic_skip_reason(semantic_result)
        if result.semantic_skip_reason and not approved_indexes:
            result.status = "skipped"
        if not gate_result.passed:
            _mark_failed_source(result, "write_gate", ValueError(_write_gate_error_message(gate_result.model_dump())))

        if write and approved_indexes:
            self.post_processor.write_approved_items(
                vault_path=vault_path,
                result=result,
                items=approved_write_items(
                    semantic_result=semantic_result,
                    approved_indexes=approved_indexes,
                    source_file=source_file,
                    privacy_config=privacy_config,
                ),
                semantic_results=[semantic_result],
            )
        result.touched_pages = _dedupe_pages([*result.generated_pages, *touched_pages, *_touched_pages(result, semantic_run.candidate_page_context)])
        result.scoped_lint = scoped_lint_payload(result)
        if write and auto_scoped_lint and result.touched_pages:
            self.post_processor.run_scoped_lint(
                result=result,
                vault_path=vault_path,
                apply_safe_fixes=auto_apply_safe_lint_fixes,
                include_related=scoped_lint_include_related,
            )
        return result

def _segment_record(batch: SourceSegmentBatch, index: int, result: IngestSourceResult) -> dict[str, object]:
    segment = batch.segments[index]
    semantic_result = result.semantic_result
    segmentation = segment.document.metadata.get("segmentation") if isinstance(segment.document.metadata, dict) else {}
    segmentation = segmentation if isinstance(segmentation, dict) else {}
    return {
        "segment_id": segment.segment_id,
        "index": segment.index,
        "title": segment.title,
        "chars": len(segment.content),
        "source_range": segment.source_range.model_dump(),
        "sibling_context_mode": segmentation.get("sibling_context_mode", "none"),
        "previous_segment_title": segmentation.get("previous_segment_title"),
        "next_segment_title": segmentation.get("next_segment_title"),
        "is_full_source": segment.is_full_source,
        "status": result.status,
        "error_stage": result.error_stage,
        "error_code": result.error_code,
        "error_category": result.error_category,
        "error_retryable": result.error_retryable,
        "error_hint": result.error_hint,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "approved_operation_indexes": list(result.approved_operation_indexes),
        "generated_pages": list(result.generated_pages),
        "touched_pages": list(result.touched_pages),
        "metrics": dict(result.metrics),
        "warnings": [*segment.warnings, *_semantic_result_warnings(semantic_result)],
        "page_plan_operations": _semantic_result_operations(semantic_result),
    }


def _semantic_result_operations(semantic_result: IngestSemanticWorkflowResult | None) -> list[dict[str, object]]:
    if semantic_result is None:
        return []
    return [
        {
            "operation_index": index,
            "action": operation.action,
            "target_page": operation.target_page,
            "page_dir": operation.page_dir,
            "canonical_path": operation.canonical_path,
            "legacy_paths": list(operation.legacy_paths),
            "page_kind": operation.page_kind,
            "subject_kind": operation.subject_kind,
            "facets": list(operation.facets),
            "title": operation.title,
            "knowledge_object": operation.knowledge_object,
            "selected_claim_ids": list(operation.selected_claim_ids),
            "selected_relation_ids": list(operation.selected_relation_ids),
            "source_digest_ids": list(operation.source_digest_ids),
            "decision_reason": operation.decision_reason,
        }
        for index, operation in enumerate(semantic_result.wiki_page_plan.operations)
    ]


def _semantic_result_warnings(semantic_result: IngestSemanticWorkflowResult | None) -> list[str]:
    if semantic_result is None:
        return []
    return [
        *semantic_result.knowledge_extract.warnings,
        *semantic_result.wiki_page_plan.warnings,
        *semantic_result.wiki_draft_batch.warnings,
        *semantic_result.ingest_draft_review.warnings,
    ]


def _combined_segment_skip_reason(segment_results: list[IngestSourceResult]) -> str | None:
    reasons = [result.semantic_skip_reason for result in segment_results if result.semantic_skip_reason]
    if len(reasons) == len(segment_results) and reasons:
        return "All source segments were skipped by semantic page planning."
    return None


def _dedupe_pages(pages: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for page in pages:
        if page and page not in seen:
            seen.add(page)
            result.append(page)
    return result


class IngestPipeline:
    """Runs connector discovery, source checkpoints, semantic ingest, and optional writes."""

    def __init__(
        self,
        semantic_workflow: IngestSemanticWorkflow,
        *,
        source_pipeline: SourcePipeline | None = None,
        write_pipeline: WikiWritePipeline | None = None,
        context_provider: IngestContextProvider | None = None,
        write_gate: IngestWriteGate | None = None,
        document_processing_pipeline: DocumentProcessingPipeline | None = None,
        checkpoint_store: CheckpointStore | None = None,
        lint_pipeline: WikiLintPipeline | None = None,
        semantic_workflow_factory: Callable[[], IngestSemanticWorkflow] | None = None,
    ) -> None:
        self.semantic_workflow = semantic_workflow
        self.semantic_workflow_factory = semantic_workflow_factory
        self.source_pipeline = source_pipeline or SourcePipeline()
        self.write_pipeline = write_pipeline or WikiWritePipeline()
        self.context_provider = context_provider or IngestContextProvider()
        self.write_gate = write_gate or IngestWriteGate()
        self.document_processing_pipeline = document_processing_pipeline or DocumentProcessingPipeline()
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self._external_lint_pipeline = lint_pipeline is not None
        self.lint_pipeline = lint_pipeline or WikiLintPipeline()
        self.source_executor = IngestSourceExecutor(
            semantic_workflow=self.semantic_workflow,
            write_pipeline=self.write_pipeline,
            context_provider=self.context_provider,
            write_gate=self.write_gate,
            checkpoint_store=self.checkpoint_store,
            lint_pipeline=self.lint_pipeline,
        )

    def _source_executor(self, *, parallel: bool) -> IngestSourceExecutor:
        if not parallel:
            return self.source_executor
        workflow = self.semantic_workflow_factory() if self.semantic_workflow_factory else self.semantic_workflow
        return IngestSourceExecutor(
            semantic_workflow=workflow,
            write_pipeline=self.write_pipeline,
            context_provider=self.context_provider,
            write_gate=self.write_gate,
            checkpoint_store=self.checkpoint_store,
            lint_pipeline=self.lint_pipeline,
        )

    def run(
        self,
        config: KnoArborConfig,
        *,
        connector_names: list[str] | None = None,
        write: bool = False,
        max_tokens: int | None = None,
        write_report: bool = True,
        append_ledger: bool = True,
        document_processing_result: DocumentProcessingResult | None = None,
    ) -> IngestPipelineResult:
        monitor = current_run_monitor()
        started_at = _now_text()
        started = time.perf_counter()
        vault_path = config.vault.path.expanduser().resolve()
        if not self._external_lint_pipeline:
            self.lint_pipeline = WikiLintPipeline(privacy_config=config.privacy)
            self.source_executor.lint_pipeline = self.lint_pipeline
            self.source_executor.post_processor.lint_pipeline = self.lint_pipeline
        if monitor:
            monitor.event("pipeline_started", stage="source_discovery", message="Starting ingest pipeline.")
        checkpoint_path = self.checkpoint_store.checkpoint_path(vault_path, "maintenance/source_ingest_checkpoints.json")
        state = self.checkpoint_store.read_state(checkpoint_path)
        index_payload = _read_index_payload(vault_path)
        ignore = KnoArborIgnore.from_file(vault_path / ".knoarborignore")
        if document_processing_result is None:
            if monitor:
                monitor.event("document_processing_started", stage="document_processing", message="Running document preprocessing.")
            document_processing_result = self.document_processing_pipeline.run(config)
            if monitor:
                monitor.event("document_processing_finished", stage="source_discovery", message="Document preprocessing finished.", payload=document_processing_result.stats)

        results: list[IngestSourceResult] = []
        discovered_source_files: set[str] = set()
        selected_connectors = selected_connector_configs(config, connector_names)
        for connector_index, (connector_name, connector_config) in enumerate(selected_connectors.items()):
            if monitor:
                monitor.event(
                    "connector_started",
                    stage="source_discovery",
                    current_item=connector_name,
                    message=f"Loading connector {connector_name}.",
                    progress={"total": len(selected_connectors), "completed": connector_index, "current": connector_name},
                )
                monitor.raise_if_cancelled()
            try:
                batch = self.source_pipeline.run(connector_name, connector_config)
            except Exception as exc:
                results.append(_failed_source_result(connector_name, "connector", exc))
                continue
            metric_key = connector_source_metric_key(connector_name, connector_config.settings)
            if metric_key:
                update_source_counts(vault_path, {metric_key: len(batch.items) + len(batch.failures)})
            if monitor:
                monitor.event(
                    "connector_finished",
                    stage="source_discovery",
                    current_item=connector_name,
                    message=f"Connector {connector_name} returned {len(batch.items)} source(s).",
                    payload={"items": len(batch.items), "failures": len(batch.failures)},
                )
            for failure in batch.failures:
                results.append(_failed_source_result_from_pipeline_failure(failure))
            discovered_source_files.update(relative_or_absolute(vault_path, Path(item.raw.raw_path)) for item in batch.items)
            results.extend(
                self._run_connector_items(
                    connector_name=connector_name,
                    items=batch.items,
                    vault_path=vault_path,
                    state=state,
                    checkpoint_path=checkpoint_path,
                    index_payload=index_payload,
                    ignore=ignore,
                    config=config,
                    write=write,
                    max_tokens=max_tokens,
                )
            )
        lifecycle_candidates = source_lifecycle_candidates(vault_path, state, discovered_source_files)

        result = IngestPipelineResult(
            results=results,
            stats={
                "source_count": len(results),
                "processed_count": sum(1 for result in results if source_processed(result)),
                "skipped_count": sum(1 for result in results if result.status == "skipped"),
                "written_count": sum(len(result.generated_pages) for result in results),
                "failed_count": sum(1 for result in results if result.status == "failed"),
                "segment_count": segment_count(results),
                "processed_segment_count": segment_status_count(results, {"processed", "written", "skipped", "rejected"}),
                "failed_segment_count": segment_status_count(results, {"failed"}),
                "max_segment_chars": max_segment_chars(results),
                "lifecycle_candidate_count": len(lifecycle_candidates),
                "document_processing_count": document_processing_result.stats.get("item_count", 0),
                "document_processing_failed_count": document_processing_result.stats.get("failed_count", 0),
                "recovery_candidate_count": recovery_candidate_count(results),
                "configured_max_concurrent_sources": config.ingest.concurrency.max_concurrent_sources,
                "effective_max_concurrent_sources": _effective_source_concurrency(config, write),
            },
            document_processing=document_processing_result,
            lifecycle_candidates=lifecycle_candidates,
        )
        result.metrics = ingest_run_metrics(results, time.perf_counter() - started)
        run_id = monitor.run_id if monitor else datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        if config.ingest.recovery.enabled:
            result.stats["execution_records"] = len(results)
            result.metrics["execution_ledger_path"] = write_ingest_execution_ledger(
                vault_path,
                result,
                run_id=run_id,
                ledger_path=config.ingest.recovery.execution_ledger_path,
            )
        if write_report or append_ledger:
            if monitor:
                monitor.event("report_write_started", stage="reporting", message="Writing ingest report and ledger.")
            ledger_path, report_path = write_ingest_run_artifacts(
                vault_path,
                result,
                started_at=started_at,
                finished_at=_now_text(),
                run_id=run_id,
                append_ledger=append_ledger,
                write_report=write_report,
            )
            result.ledger_path = ledger_path
            result.report_path = report_path
            if monitor:
                monitor.event("report_written", stage="reporting", message="Ingest report written.", payload={"report_path": report_path, "ledger_path": ledger_path})
        return result

    def _run_connector_items(
        self,
        *,
        connector_name: str,
        items: list[SourcePipelineItem],
        vault_path: Path,
        state: dict[str, object],
        checkpoint_path: Path,
        index_payload: dict[str, object],
        ignore: KnoArborIgnore,
        config: KnoArborConfig,
        write: bool,
        max_tokens: int | None,
    ) -> list[IngestSourceResult]:
        monitor = current_run_monitor()
        effective_concurrency = _effective_source_concurrency(config, write)
        for item_index, item in enumerate(items):
            if monitor:
                monitor.event(
                    "source_queued",
                    stage="source_discovery",
                    current_item=item.raw.source_id,
                    message=f"Queued source {item_index + 1}/{len(items)} from {connector_name}.",
                    progress={"total": len(items), "completed": item_index, "current": item.raw.source_id},
                )
                monitor.raise_if_cancelled()
        if effective_concurrency <= 1 or len(items) <= 1:
            return [
                self.source_executor.run_item(
                    connector_name=connector_name,
                    item=item,
                    vault_path=vault_path,
                    state=state,
                    checkpoint_path=checkpoint_path,
                    index_payload=index_payload,
                    ignore=ignore,
                    privacy_config=config.privacy,
                    write=write,
                    max_tokens=max_tokens,
                    auto_scoped_lint=config.ingest.auto_scoped_lint,
                    auto_apply_safe_lint_fixes=config.ingest.auto_apply_safe_lint_fixes,
                    scoped_lint_include_related=config.lint.scoped_include_related,
                    segmentation_config=config.ingest.segmentation,
                )
                for item in items
            ]
        results_by_index: dict[int, IngestSourceResult] = {}
        with ThreadPoolExecutor(max_workers=effective_concurrency, thread_name_prefix="knoarbor-ingest-source") as executor:
            futures = {
                executor.submit(
                    self._source_executor(parallel=True).run_item,
                    connector_name=connector_name,
                    item=item,
                    vault_path=vault_path,
                    state=state,
                    checkpoint_path=checkpoint_path,
                    index_payload=index_payload,
                    ignore=ignore,
                    privacy_config=config.privacy,
                    write=write,
                    max_tokens=max_tokens,
                    auto_scoped_lint=config.ingest.auto_scoped_lint,
                    auto_apply_safe_lint_fixes=config.ingest.auto_apply_safe_lint_fixes,
                    scoped_lint_include_related=config.lint.scoped_include_related,
                    segmentation_config=config.ingest.segmentation,
                ): item_index
                for item_index, item in enumerate(items)
            }
            for future in as_completed(futures):
                results_by_index[futures[future]] = future.result()
        return [results_by_index[index] for index in sorted(results_by_index)]

    def run_document(
        self,
        document: SourceDocument,
        *,
        vault_path: Path,
        write: bool = False,
        max_tokens: int | None = None,
        privacy_config: PrivacyConfig | None = None,
        write_report: bool = True,
        append_ledger: bool = True,
        auto_scoped_lint: bool = True,
        auto_apply_safe_lint_fixes: bool = True,
        scoped_lint_include_related: bool = True,
        segmentation_config: IngestSegmentationConfig | None = None,
    ) -> IngestSourceResult:
        monitor = current_run_monitor()
        started_at = _now_text()
        started = time.perf_counter()
        vault_path = vault_path.expanduser().resolve()
        result = self.source_executor.run_document(
            document,
            vault_path=vault_path,
            privacy_config=privacy_config or PrivacyConfig(),
            write=write,
            max_tokens=max_tokens,
            auto_scoped_lint=auto_scoped_lint,
            auto_apply_safe_lint_fixes=auto_apply_safe_lint_fixes,
            scoped_lint_include_related=scoped_lint_include_related,
            segmentation_config=segmentation_config or IngestSegmentationConfig(),
        )
        if write_report or append_ledger:
            run_result = IngestPipelineResult(
                results=[result],
                stats={
                    "source_count": 1,
                    "processed_count": 1 if source_processed(result) else 0,
                    "skipped_count": 0 if result.status != "skipped" else 1,
                    "written_count": len(result.generated_pages),
                    "failed_count": 1 if result.status == "failed" else 0,
                    "segment_count": segment_count([result]),
                    "processed_segment_count": segment_status_count([result], {"processed", "written", "skipped", "rejected"}),
                    "failed_segment_count": segment_status_count([result], {"failed"}),
                    "max_segment_chars": max_segment_chars([result]),
                    "recovery_candidate_count": recovery_candidate_count([result]),
                },
            )
            run_result.metrics = ingest_run_metrics([result], time.perf_counter() - started)
            ledger_path, report_path = write_ingest_run_artifacts(
                vault_path,
                run_result,
                started_at=started_at,
                finished_at=_now_text(),
                run_id=monitor.run_id if monitor else None,
                append_ledger=append_ledger,
                write_report=write_report,
            )
            result.ledger_path = ledger_path
            result.report_path = report_path
        return result


def _read_index_payload(vault_path: Path) -> dict[str, object]:
    import json

    from knoarbor.storage.wiki_index import ensure_machine_index, machine_index_dir

    ensure_machine_index(vault_path)
    index_dir = machine_index_dir(vault_path)
    manifest_path = index_dir / "manifest.json"
    graph_path = index_dir / "graph_index.json"
    if not manifest_path.exists() or not graph_path.exists():
        return {"available": False, "path": ".knoarbor/index", "content": ""}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    summary = {
        "manifest": manifest,
        "node_count": len(graph.get("nodes", [])) if isinstance(graph.get("nodes"), list) else 0,
        "edge_count": len(graph.get("edges", [])) if isinstance(graph.get("edges"), list) else 0,
        "source_count": len(graph.get("sources", [])) if isinstance(graph.get("sources"), list) else 0,
    }
    return {"available": True, "path": ".knoarbor/index/manifest.json", "content": json.dumps(summary, ensure_ascii=False, sort_keys=True)}


def _effective_source_concurrency(config: KnoArborConfig, write: bool) -> int:
    configured = config.ingest.concurrency.max_concurrent_sources
    if write:
        return 1
    return configured


def _is_ignored(ignore: KnoArborIgnore, vault_path: Path, raw_path: Path, source_file: str) -> bool:
    candidates = [source_file, raw_path.name, str(raw_path)]
    try:
        candidates.append(raw_path.expanduser().resolve().relative_to(vault_path).as_posix())
    except ValueError:
        pass
    return any(ignore.ignored(candidate) for candidate in candidates)


def _approved_ingest_operation_indexes(result: IngestSemanticWorkflowResult) -> set[int]:
    decisions = {
        decision.operation_index: decision
        for decision in result.ingest_draft_review.decisions
        if decision.decision == "approve"
        and decision.write_safety in {"safe_create", "safe_update"}
        and _review_checks_allow_write(decision.checks.model_dump())
    }
    return {
        draft.operation_index
        for draft in result.wiki_draft_batch.drafts
        if draft.operation_index in decisions
    }


def _review_checks_allow_write(checks: dict[str, object]) -> bool:
    hard_checks = [
        "operation_aligned",
        "source_trace_complete",
        "atom_coverage_sufficient",
        "page_boundary_clear",
        "identity_fit",
        "source_supported",
        "not_duplicate",
        "synthesis_quality",
        "maintainable",
        "update_safe",
        "write_safe",
    ]
    return all(bool(checks.get(check)) for check in hard_checks)


def _semantic_skip_reason(result: IngestSemanticWorkflowResult) -> str | None:
    operations = result.wiki_page_plan.operations
    if not operations or any(operation.action != "skip" for operation in operations):
        return None
    return operations[0].decision_reason or "Semantic page planning skipped this source."


def _redaction_payload(enabled: bool, counts: dict[str, int]) -> dict[str, object]:
    return {
        "enabled": enabled,
        "counts": counts,
        "redacted_count": sum(counts.values()),
    }


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _touched_pages(source_result: IngestSourceResult, candidate_page_context: object) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for path in [*source_result.generated_pages, *[page.path for page in getattr(candidate_page_context, "pages", []) if page.exists]]:
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _failed_source_result(connector_name: str, stage: str, exc: Exception) -> IngestSourceResult:
    info = error_info(exc)
    return IngestSourceResult(
        connector=connector_name,
        source_id=f"{connector_name}:connector-error",
        source_file=connector_name,
        should_process=False,
        mode="failed",
        reason=f"{stage} failed.",
        status="failed",
        error_stage=stage,
        error_code=str(info["code"]),
        error_category=str(info["category"]),
        error_retryable=bool(info["retryable"]),
        error_hint=str(info["hint"]),
        error_type=type(exc).__name__,
        error_message=str(exc),
    )


def _failed_source_result_from_pipeline_failure(failure: SourcePipelineFailure) -> IngestSourceResult:
    return IngestSourceResult(
        connector=failure.connector,
        source_id=failure.ref.source_id,
        source_file=failure.ref.uri,
        should_process=False,
        mode="failed",
        reason=f"{failure.stage} failed.",
        status="failed",
        error_stage=failure.stage,
        error_code=failure.error_code,
        error_category=failure.error_category,
        error_retryable=failure.error_retryable,
        error_hint=failure.error_hint,
        error_type=failure.error_type,
        error_message=failure.error_message,
    )


def _mark_failed_source(result: IngestSourceResult, stage: str, exc: Exception) -> None:
    info = error_info(exc)
    result.status = "failed"
    result.error_stage = stage
    result.error_code = str(info["code"])
    result.error_category = str(info["category"])
    result.error_retryable = bool(info["retryable"])
    result.error_hint = str(info["hint"])
    result.error_type = type(exc).__name__
    result.error_message = str(exc)


def _copy_source_error(target: IngestSourceResult, source: IngestSourceResult, *, fallback_stage: str) -> None:
    target.status = "failed"
    target.error_stage = source.error_stage or fallback_stage
    target.error_code = source.error_code
    target.error_category = source.error_category
    target.error_retryable = source.error_retryable
    target.error_hint = source.error_hint
    target.error_type = source.error_type
    target.error_message = source.error_message


def _write_gate_error_message(gate_payload: dict[str, object]) -> str:
    issues = gate_payload.get("issues")
    if not isinstance(issues, list) or not issues:
        return "Ingest write gate failed."
    messages = []
    for issue in issues[:5]:
        if isinstance(issue, dict):
            messages.append(f"{issue.get('code')}: {issue.get('message')}")
    return "; ".join(messages) or "Ingest write gate failed."
