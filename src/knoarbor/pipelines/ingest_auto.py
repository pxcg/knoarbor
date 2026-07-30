from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import Context, copy_context
from pathlib import Path
from typing import Any
import time

from knoarbor.core.config import IngestSegmentationConfig, PrivacyConfig
from knoarbor.core.evidence_alignment import canonical_evidence_text
from knoarbor.core.errors import error_info
from knoarbor.core.hashing import content_hash
from knoarbor.core.markdown import extract_heading, inline_text
from knoarbor.core.redaction import redact_source_document
from knoarbor.core.schemas.ingest_pipeline import IngestPipelineResult, IngestSourceResult
from knoarbor.core.schemas.knowledge_atoms import KnowledgeEvidenceSpan
from knoarbor.core.schemas.source_metadata import KnowledgeSource
from knoarbor.core.schemas.index_metadata_extract import IndexMetadataExtractResult
from knoarbor.core.schemas.source_record import SourceRecord, SourceRecordAttachment, SourceRecordContribution, SourceRecordUnit
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.source_unitization import attach_source_unitization
from knoarbor.audit.ingest_report import write_ingest_run_artifacts
from knoarbor.pipelines.ingest_metrics import (
    ingest_run_metrics,
    max_segment_chars,
    recovery_candidate_count,
    semantic_attempt_metrics,
    segment_count,
    segment_status_count,
    source_processed,
)
from knoarbor.core.schemas.ingest_execution import FactIdentity, IngestExecutionPort
from knoarbor.pipelines.index_metadata_atoms import (
    compile_extracted_index_metadata,
    document_body as _document_body,
    dominant_source_language as _dominant_source_language,
    source_text_language as _source_text_language,
)
from knoarbor.pipelines.ingest_publication import publish_ingest_source, session_window
from knoarbor.pipelines.source_segmentation import SourceSegmentBatch, SourceSegmenter
from knoarbor.runtime import current_run_monitor, vault_write_lock
from knoarbor.runtime.run_monitor import RunCancelled
from knoarbor.runtime.provider_permits import provider_permit_pool, rate_limit_delay_seconds
from knoarbor.runtime.reporter import RunReporter
from knoarbor.runtime.ingest_exceptions import ProviderRateLimited
from knoarbor.semantic.metrics import summarize_semantic_runs
from knoarbor.semantic.runner import SemanticRunFailed, SemanticRunner
from knoarbor.pipelines.ingest_compilation import (
    IngestCompilationIntegrityError,
    IndexExtractResult,
    merge_segment_extracts as _merge_segment_extracts,
    merge_semantic_metrics as _merge_semantic_metrics,
    validate_compiled_index_metadata,
)
from knoarbor.storage.entity_registry import prepare_entity_identity_resolution
from knoarbor.storage.source_records import source_identity


INGEST_PROFILE = "auto"


class IndexMetadataExtractionFailed(Exception):
    """A failed extractor call with metrics owned by that one source segment."""

    def __init__(self, cause: Exception, semantic_metrics: dict[str, object]) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.semantic_metrics = semantic_metrics


class SegmentBatchCompilationFailed(Exception):
    """A segment batch failure with metrics from this batch only."""

    def __init__(
        self,
        cause: Exception,
        semantic_metrics: dict[str, object],
        *,
        completed_segment_indexes: list[int],
        failed_segment_indexes: list[int],
    ) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.semantic_metrics = semantic_metrics
        self.completed_segment_indexes = completed_segment_indexes
        self.failed_segment_indexes = failed_segment_indexes
        self.segment_semantic_metrics: dict[int, dict[str, object]] = {}


class IndexMetadataExtractor:
    """Single-call semantic extractor for the index metadata ingest profile."""

    def __init__(self, runner: SemanticRunner, *, max_provider_requests: int = 2, vault_path: Path | None = None) -> None:
        self.runner = runner
        self.max_provider_requests = max_provider_requests
        self.vault_path = vault_path.expanduser().resolve() if vault_path else None

    def compile(
        self,
        document: SourceDocument,
        *,
        source_file: str,
        source_record: SourceRecord,
        max_tokens: int | None = None,
    ) -> IndexExtractResult:
        client = self.runner.client
        key = f"{getattr(client, 'provider', '')}:{getattr(client, 'model', '')}:{getattr(client, 'base_url', '')}"
        monitor = current_run_monitor()
        vault_path = monitor.vault_path if monitor else self.vault_path
        if vault_path is None:
            raise RuntimeError("Index metadata extraction needs a vault path for provider admission.")

        def on_wait(reason: str, seconds: float) -> None:
            RunReporter.current().model_admission_waiting(
                contract_name="index_metadata_extract",
                reason=reason,
                wait_seconds=seconds,
                provider_key=key,
            )

        try:
            with provider_permit_pool.acquire(
                key,
                limit=self.max_provider_requests,
                vault_path=vault_path,
                raise_if_cancelled=monitor.raise_if_cancelled if monitor else None,
                on_wait=on_wait,
                defer_on_cooldown=monitor is not None,
            ):
                result = self.runner.run_with_failure(
                    "index_metadata_extract",
                    _index_metadata_extract_payload(document, source_file, source_record),
                    max_tokens=max_tokens,
                )
            provider_permit_pool.record_success(key)
        except SemanticRunFailed as exc:
            if _is_rate_limited(exc.cause):
                cooldown_until = provider_permit_pool.impose_cooldown(key, seconds=rate_limit_delay_seconds(exc.cause))
                raise ProviderRateLimited(key, cooldown_until, exc.cause) from exc
            raise IndexMetadataExtractionFailed(exc.cause, summarize_semantic_runs([exc.failure])) from exc
        except (RunCancelled, ProviderRateLimited):
            raise
        except Exception as exc:
            if _is_rate_limited(exc):
                cooldown_until = provider_permit_pool.impose_cooldown(key, seconds=rate_limit_delay_seconds(exc))
                raise ProviderRateLimited(key, cooldown_until, exc) from exc
            raise
        compiled = result.output
        if not isinstance(compiled, IndexMetadataExtractResult):
            raise TypeError(f"Expected IndexMetadataExtractResult, got {type(compiled).__name__}")
        semantic_metrics = summarize_semantic_runs([result])
        try:
            compilation = compile_extracted_index_metadata(compiled, source_record=source_record, source_file=source_file)
        except ValueError as exc:
            raise IngestCompilationIntegrityError(
                f"Index metadata compiler failed after schema validation: {exc}"
            ) from exc
        return IndexExtractResult(
            knowledge_atom_batch=compilation.atom_batch,
            synthesis_topics=compiled.synthesis_topics,
            ambiguities=[item.model_dump(mode="json") for item in compilation.ambiguities],
            semantic_metrics=semantic_metrics,
            compilation_diagnostics=compilation.diagnostics,
            segment_semantic_metrics=(semantic_metrics,),
        )


def _is_rate_limited(exc: Exception) -> bool:
    text = str(exc).casefold()
    return "429" in text or "rate limit" in text or "quota" in text or "too many requests" in text


class AutoIngestPipeline:
    """Fast single-call semantic ingest that writes raw-grounded indexes."""

    def __init__(
        self,
        *,
        extractor: IndexMetadataExtractor | None = None,
    ) -> None:
        self.extractor = extractor

    def run_document(
        self,
        document: SourceDocument,
        *,
        vault_path: Path,
        write: bool = False,
        privacy_config: PrivacyConfig | None = None,
        segmentation_config: IngestSegmentationConfig | None = None,
        max_concurrent_segments: int = 1,
        initial_concurrent_segments: int = 1,
        write_report: bool = True,
        append_ledger: bool = True,
        max_tokens: int | None = None,
        execution: IngestExecutionPort | None = None,
    ) -> IngestSourceResult:
        monitor = current_run_monitor()
        started_at = _now_text()
        started = time.perf_counter()
        vault_path = vault_path.expanduser().resolve()
        result = IngestSourceResult(
            connector=document.origin.connector,
            source_id=document.source_id,
            source_file=document.origin.raw_path,
            should_process=True,
            mode=document.checkpoint.mode,
            reason="Explicit source document input.",
            ingest_profile=INGEST_PROFILE,
        )
        try:
            self._write_document(
                result=result,
                document=document,
                vault_path=vault_path,
                source_file=document.origin.raw_path,
                privacy_config=privacy_config or PrivacyConfig(),
                segmentation_config=segmentation_config,
                max_concurrent_segments=max_concurrent_segments,
                initial_concurrent_segments=initial_concurrent_segments,
                write=write,
                max_tokens=max_tokens,
                execution=execution,
            )
        except RunCancelled:
            raise
        except Exception as exc:
            stage = "index_metadata_validation" if isinstance(exc, IngestCompilationIntegrityError) else "auto_write"
            _mark_failed_source(result, stage, exc)
        result.metrics["elapsed_seconds"] = time.perf_counter() - started
        result.metrics.setdefault("semantic", _empty_semantic_metrics())
        result.context.setdefault("ingest_profile", INGEST_PROFILE)
        if write_report or append_ledger:
            run_result = IngestPipelineResult(
                ingest_profile=INGEST_PROFILE,
                results=[result],
                stats={
                    "source_count": 1,
                    "processed_count": 1 if source_processed(result) else 0,
                    "skipped_count": 0 if result.status != "skipped" else 1,
                    "written_count": len(result.generated_pages),
                    "failed_count": 1 if result.status == "failed" else 0,
                    "partial_count": 1 if result.status == "partial" else 0,
                    "segment_count": segment_count([result]),
                    "processed_segment_count": segment_status_count([result], {"processed", "written", "skipped"}),
                    "failed_segment_count": segment_status_count([result], {"failed"}),
                    "max_segment_chars": max_segment_chars([result]),
                    "recovery_candidate_count": recovery_candidate_count([result]),
                    "configured_max_concurrent_segments": max_concurrent_segments,
                },
            )
            run_result.metrics = ingest_run_metrics([result], time.perf_counter() - started)
            run_result.metrics["semantic_attempts"] = semantic_attempt_metrics(monitor.events_path if monitor else None)
            run_result.metrics["ingest_profile"] = INGEST_PROFILE
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

    def run_generation(
        self,
        documents: list[SourceDocument],
        *,
        resolver_failures: list[dict[str, object]],
        vault_path: Path,
        write: bool,
        privacy_config: PrivacyConfig,
        segmentation_config: IngestSegmentationConfig,
        max_concurrent_segments: int,
        initial_concurrent_segments: int,
        write_report: bool,
        append_ledger: bool,
        max_tokens: int | None,
        execution: IngestExecutionPort | None = None,
    ) -> IngestPipelineResult:
        monitor = current_run_monitor()
        started_at = _now_text()
        started = time.perf_counter()
        results: list[IngestSourceResult | None] = [None] * len(documents)
        if len(documents) <= 1:
            for position, document in enumerate(documents):
                results[position] = self.run_document(
                    document,
                    vault_path=vault_path,
                    write=write,
                    privacy_config=privacy_config,
                    segmentation_config=segmentation_config,
                    max_concurrent_segments=max_concurrent_segments,
                    initial_concurrent_segments=initial_concurrent_segments,
                    write_report=False,
                    append_ledger=False,
                    max_tokens=max_tokens,
                    execution=execution,
                )
        else:
            # Each immutable source is independent until factual publication.
            # Run ready sources concurrently, retain input order in the result,
            # and let the process-wide provider permit pool own aggregate model
            # request capacity across every source.
            with ThreadPoolExecutor(max_workers=min(len(documents), max_concurrent_segments)) as executor:
                futures = {
                    executor.submit(
                        copy_context().run,
                        self.run_document,
                        document,
                        vault_path=vault_path,
                        write=write,
                        privacy_config=privacy_config,
                        segmentation_config=segmentation_config,
                        max_concurrent_segments=max_concurrent_segments,
                        initial_concurrent_segments=initial_concurrent_segments,
                        write_report=False,
                        append_ledger=False,
                        max_tokens=max_tokens,
                        execution=execution,
                    ): position
                    for position, document in enumerate(documents)
                }
                for future in as_completed(futures):
                    RunReporter.current().raise_if_cancelled()
                    results[futures[future]] = future.result()
        ordered_results = [item for item in results if item is not None]
        if len(ordered_results) != len(documents):
            raise RuntimeError("Source execution finished without a result for every document.")
        results = ordered_results
        results.extend(_failed_source_result_from_resolver(item) for item in resolver_failures)
        result = IngestPipelineResult(
            ingest_profile=INGEST_PROFILE,
            results=results,
            stats={
                "source_count": len(results),
                "processed_count": sum(1 for item in results if source_processed(item)),
                "skipped_count": sum(1 for item in results if item.status == "skipped"),
                "written_count": sum(len(item.generated_pages) for item in results),
                "failed_count": sum(1 for item in results if item.status == "failed"),
                "partial_count": sum(1 for item in results if item.status == "partial"),
                "segment_count": segment_count(results),
                "processed_segment_count": segment_status_count(results, {"processed", "written", "skipped"}),
                "failed_segment_count": segment_status_count(results, {"failed"}),
                "max_segment_chars": max_segment_chars(results),
                "recovery_candidate_count": recovery_candidate_count(results),
                "configured_max_concurrent_segments": max_concurrent_segments,
            },
        )
        result.metrics = ingest_run_metrics(results, time.perf_counter() - started)
        result.metrics["semantic_attempts"] = semantic_attempt_metrics(monitor.events_path if monitor else None)
        result.metrics["ingest_profile"] = INGEST_PROFILE
        if write_report or append_ledger:
            ledger_path, report_path = write_ingest_run_artifacts(
                vault_path,
                result,
                started_at=started_at,
                finished_at=_now_text(),
                run_id=monitor.run_id if monitor else None,
                append_ledger=append_ledger,
                write_report=write_report,
            )
            result.ledger_path = ledger_path
            result.report_path = report_path
        return result

    def _write_document(
        self,
        *,
        result: IngestSourceResult,
        document: SourceDocument,
        vault_path: Path,
        source_file: str,
        privacy_config: PrivacyConfig,
        segmentation_config: IngestSegmentationConfig | None,
        max_concurrent_segments: int,
        initial_concurrent_segments: int,
        write: bool,
        max_tokens: int | None = None,
        execution: IngestExecutionPort | None = None,
    ) -> None:
        monitor = current_run_monitor()
        redacted = redact_source_document(document, privacy_config)
        unitized_document = attach_source_unitization(redacted.document)
        model_source_file = unitized_document.origin.raw_path or source_file
        raw_record_id, raw_revision_id = source_identity(unitized_document, source_path=model_source_file)
        base_source_record = _auto_source_record(unitized_document, model_source_file)
        if write:
            if execution is None:
                raise RuntimeError("Factual ingest publication requires an explicit execution port.")
            publication = session_window(unitized_document)
            existing = execution.find_published_fact(
                FactIdentity(
                    source_id=raw_record_id,
                    raw_revision_id=raw_revision_id,
                    window_id=str(publication["window_id"]) if publication.get("window_id") else None,
                )
            )
            if existing is not None:
                result.status = "skipped"
                result.should_process = False
                result.reason = "The factual source revision is already committed."
                result.semantic_skip_reason = "committed_source_revision"
                result.context["source_revision"] = {
                    "revision_id": existing.revision_id,
                    "generation_path": str(existing.generation_path.relative_to(vault_path)),
                }
                return
        segment_batch = SourceSegmenter(segmentation_config).segment(unitized_document)
        segment_source_records, source_record = _source_records_for_segment_batch(segment_batch, base_source_record, model_source_file)
        result.redaction = {
            "enabled": redacted.enabled,
            "counts": redacted.counts,
            "redacted_count": sum(redacted.counts.values()),
        }
        result.context["ingest_profile"] = INGEST_PROFILE
        result.context["index_metadata"] = {
            "strategy": "auto_index_metadata_extraction",
            "model_calls": len(segment_batch.segments),
            "source_record_id": source_record.record_id,
        }
        result.context["source_unitization"] = unitized_document.metadata.get("source_unitization", {})
        result.segmentation = segment_batch.summary()
        result.segments = [
            {
                "index": segment.index,
                "title": segment.title,
                "chars": len(segment.content),
                "status": "queued",
            }
            for segment in segment_batch.segments
        ]
        compiler = self._require_compiler()
        if monitor:
            monitor.event(
                "index_metadata_extract_started",
                status="running",
                stage="index_metadata_extract",
                current_item=result.source_id,
                message="Running auto index metadata ingest extractor.",
                payload={"ingest_profile": INGEST_PROFILE, "segments": len(segment_batch.segments)},
            )
        try:
            compiled = _compile_segment_batch(
                compiler,
                segment_batch,
                segment_source_records,
                source_file=model_source_file,
                source_record=source_record,
                max_tokens=max_tokens,
                max_concurrent_segments=max_concurrent_segments,
                initial_concurrent_segments=initial_concurrent_segments,
                execution=execution,
            )
        except SegmentBatchCompilationFailed as exc:
            result.context["semantic_metrics"] = exc.semantic_metrics
            result.metrics = {"elapsed_seconds": 0, "semantic": exc.semantic_metrics}
            failure = error_info(exc.cause)
            for segment in result.segments:
                index = int(segment["index"])
                segment_semantic = exc.segment_semantic_metrics.get(index)
                if segment_semantic:
                    segment["metrics"] = {
                        "elapsed_seconds": segment_semantic.get("elapsed_seconds"),
                        "semantic": segment_semantic,
                    }
                if index in exc.completed_segment_indexes:
                    segment["status"] = "processed"
                elif index in exc.failed_segment_indexes:
                    segment.update(
                        {
                            "status": "failed",
                            "error_code": failure["code"],
                            "error_category": failure["category"],
                            "error_retryable": failure["retryable"],
                            "error_message": str(exc.cause),
                        }
                    )
                else:
                    segment["status"] = "not_processed"
            raise exc.cause from exc
        source_record = source_record.model_copy(
            update={
                "summary": compiled.synthesis or source_record.summary,
                "source_focus": source_record.source_focus,
            }
        )
        result.context["semantic_metrics"] = compiled.semantic_metrics
        result.context["index_metadata"]["compilation"] = compiled.compilation_diagnostics
        result.metrics = {"elapsed_seconds": 0, "semantic": compiled.semantic_metrics}
        for segment in result.segments:
            segment["status"] = "processed"
        for segment, segment_semantic in zip(
            result.segments,
            compiled.segment_semantic_metrics,
            strict=False,
        ):
            segment["metrics"] = {
                "elapsed_seconds": segment_semantic.get("elapsed_seconds"),
                "semantic": segment_semantic,
            }
        result.context["index_metadata"]["synthesis"] = compiled.synthesis
        result.context["index_metadata"]["ambiguities"] = compiled.ambiguities
        validate_compiled_index_metadata(compiled, source_record_id=source_record.record_id)
        candidate_claims = int(compiled.compilation_diagnostics.get("candidates", {}).get("claims", 0))
        accepted_claims = int(compiled.compilation_diagnostics.get("accepted", {}).get("claims", 0))
        if candidate_claims and not accepted_claims:
            result.status = "partial"
            result.reason = "No grounded claims passed candidate-local evidence validation."
        else:
            result.status = "processed"
            result.reason = "Index metadata compiled successfully."
        if monitor:
            monitor.event(
                "index_metadata_extract_finished",
                status="running",
                stage="index_metadata_extract",
                current_item=result.source_id,
                message="Auto extractor produced index metadata.",
                payload={"semantic": compiled.semantic_metrics},
            )
        if not write:
            return
        # The model phase never mutates a vault. Identity resolution uses only
        # published source contributions; factual publication is the sole write
        # boundary; vault-level materialization is deliberately outside it.
        with vault_write_lock(vault_path):
            if monitor:
                monitor.raise_if_cancelled()
            identity_resolution = prepare_entity_identity_resolution(
                vault_path,
                compiled.knowledge_atom_batch,
                raw_record_id=raw_record_id,
            )
            resolved_atom_batch = identity_resolution.atom_batch
            result.context["entity_identity"] = {
                "registry_bound": True,
                "entity_ids": [entity.atom_id for entity in resolved_atom_batch.entities if entity.atom_id],
            }
            publication = publish_ingest_source(
                vault_path,
                result=result,
                document=unitized_document,
                source_record=source_record,
                source_file=model_source_file,
                atom_batch=resolved_atom_batch,
                execution=execution,
                ingest_profile=INGEST_PROFILE,
                run_id=monitor.run_id if monitor else "",
            )
            processing_record = publication.processing_record
            published = publication.published_fact
            result.context["source_revision"] = {
                "revision_id": published.revision_id,
                "generation_path": str(published.generation_path.relative_to(vault_path)),
            }
            result.context["index_metadata"]["processing_record_id"] = processing_record.processing_record_id
            result.context["index_metadata"]["raw_record_id"] = processing_record.raw_record_id
            result.context["index_metadata"]["raw_evidence_units"] = len(processing_record.source_units)
            result.context["raw_grounded"] = {
                "processing_record_id": processing_record.processing_record_id,
                "raw_record_id": processing_record.raw_record_id,
                "source_unit_count": len(processing_record.source_units),
                "raw_evidence_units": len(processing_record.source_units),
            }
            result.context["materialization"] = {"revision_id": published.revision_id, "state": "requested"}
            result.generated_pages = list(processing_record.page_paths)
            result.touched_pages = list(processing_record.page_paths)
        result.wrote = True
        if result.status == "partial":
            result.reason = "Raw source committed, but no grounded claims passed evidence validation."
        else:
            result.reason = "Index metadata ingest committed a raw-grounded source revision."
        if monitor:
            monitor.event(
                "auto_indexes_written",
                status="running",
                stage="indexing",
                current_item=result.source_id,
                message="Index metadata ingest wrote source, raw evidence, and atom indexes.",
                payload={
                    "generated_pages": result.generated_pages,
                    "source_revision_id": published.revision_id,
                    "materialization_requested": True,
                    "ingest_profile": INGEST_PROFILE,
                },
            )

    def _require_compiler(self) -> IndexMetadataExtractor:
        if self.extractor is None:
            raise RuntimeError("Index metadata ingest requires a configured index metadata ingest extractor.")
        return self.extractor


def _source_records_for_segment_batch(
    segment_batch: SourceSegmentBatch,
    base_record: SourceRecord,
    source_file: str,
) -> tuple[list[SourceRecord], SourceRecord]:
    if len(segment_batch.segments) == 1 and segment_batch.segments[0].is_full_source:
        return [base_record], base_record

    segment_records: list[SourceRecord] = []
    merged_units: list[SourceRecordUnit] = []
    next_unit_index = 0
    for segment in segment_batch.segments:
        segment_document = attach_source_unitization(segment.document)
        segment_record = _auto_source_record(segment_document, source_file)
        segment_units: list[SourceRecordUnit] = []
        for unit in segment_record.units:
            unit_index = next_unit_index
            next_unit_index += 1
            evidence = unit.evidence.model_copy(
                update={
                    "source_record_id": base_record.record_id,
                    "source_unit_index": unit_index,
                    "source_unit_id": f"U{unit_index}",
                }
            )
            metadata = {
                **unit.metadata,
                "segment_index": segment.index,
                "segment_title": segment.title,
                "segment_id": segment.segment_id,
            }
            segment_units.append(unit.model_copy(update={"index": unit_index, "evidence": evidence, "metadata": metadata}))
        segment_records.append(_source_record_with_units(base_record, segment_units))
        merged_units.extend(segment_units)

    merged_record = _source_record_with_units(base_record, merged_units)
    return segment_records, merged_record


def _source_record_with_units(base_record: SourceRecord, units: list[SourceRecordUnit]) -> SourceRecord:
    return base_record.model_copy(
        update={
            "units": units,
            "contribution_map": [
                SourceRecordContribution(
                    item_id="Q1",
                    contribution=f"Indexed {base_record.source_focus or base_record.source.title} through the raw-grounded ingest chain.",
                    evidence_unit_ids=[f"U{unit.index}" for unit in units],
                    status="accepted",
                )
            ],
        }
    )


def _compile_segment_batch(
    compiler: IndexMetadataExtractor,
    segment_batch: SourceSegmentBatch,
    segment_source_records: list[SourceRecord],
    *,
    source_file: str,
    source_record: SourceRecord,
    max_tokens: int | None,
    max_concurrent_segments: int = 1,
    initial_concurrent_segments: int = 1,
    execution: IngestExecutionPort | None = None,
) -> IndexExtractResult:
    compile_inputs = list(zip(segment_batch.segments, segment_source_records, strict=True))
    extracts: list[IndexExtractResult | None] = [None] * len(compile_inputs)
    pending = [(position, segment, segment_record) for position, (segment, segment_record) in enumerate(compile_inputs)]

    def persist(position: int, extract: IndexExtractResult) -> None:
        extracts[position] = extract

    if max_concurrent_segments == 1 or len(pending) == 1:
        for position, segment, segment_record in pending:
            RunReporter.current().raise_if_cancelled()
            try:
                if execution is not None:
                    execution.before_model_call()
                persist(
                    position,
                    compiler.compile(
                        segment.document,
                        source_file=source_file,
                        source_record=segment_record,
                        max_tokens=max_tokens,
                    ),
                )
            except Exception as exc:
                failure = _segment_batch_failure(extracts, [(position, exc)])
                if failure is not None:
                    raise failure from exc
                raise
    elif pending:
        # Model work has no vault-side effects. Preserve the segment order for
        # deterministic ids, synthesis, and audit output after parallel calls.
        # A fully successful wave grows the next wave by one. This discovers
        # useful provider capacity without a user-set fixed limit or an
        # unrelated hard maximum.
        wave_size = max(1, min(initial_concurrent_segments, max_concurrent_segments, len(pending)))
        cursor = 0
        while cursor < len(pending):
            RunReporter.current().raise_if_cancelled()
            wave = pending[cursor : cursor + wave_size]
            with ThreadPoolExecutor(max_workers=len(wave)) as executor:
                futures = {
                    executor.submit(
                        _compile_in_context,
                        copy_context(),
                        compiler,
                        segment.document,
                        source_file,
                        segment_record,
                        max_tokens,
                        execution,
                    ): position
                    for position, segment, segment_record in wave
                }
                failures: list[tuple[int, BaseException]] = []
                for future in as_completed(futures):
                    RunReporter.current().raise_if_cancelled()
                    try:
                        persist(futures[future], future.result())
                    except BaseException as exc:
                        failures.append((futures[future], exc))
            if failures:
                failure = _segment_batch_failure(extracts, failures)
                if failure is not None:
                    raise failure from failure.cause
                raise failures[0][1]
            cursor += len(wave)
            wave_size = min(wave_size + 1, max_concurrent_segments, len(pending) - cursor)
    complete_extracts = [extract for extract in extracts if extract is not None]
    if len(complete_extracts) != len(compile_inputs):
        raise RuntimeError("Segment extraction finished without a result for every segment.")
    # A full-source document retains the model's original atom ids. Segmented
    # sources need deterministic prefixes to avoid collisions during merge.
    if len(complete_extracts) == 1 and segment_batch.segments[0].is_full_source:
        extract = complete_extracts[0]
        return (
            extract
            if extract.segment_semantic_metrics
            else replace(extract, segment_semantic_metrics=(extract.semantic_metrics,))
        )
    return _merge_segment_extracts(complete_extracts, source_record.record_id)


def _segment_batch_failure(
    extracts: list[IndexExtractResult | None], failures: list[tuple[int, BaseException]]
) -> SegmentBatchCompilationFailed | None:
    metrics = [extract.semantic_metrics for extract in extracts if extract is not None]
    model_failures = [(index, exc) for index, exc in failures if isinstance(exc, IndexMetadataExtractionFailed)]
    if not model_failures:
        return None
    metrics.extend(exc.semantic_metrics for _, exc in model_failures)
    first = model_failures[0][1]
    failure = SegmentBatchCompilationFailed(
        first.cause,
        _merge_semantic_metrics(metrics),
        completed_segment_indexes=[index for index, extract in enumerate(extracts) if extract is not None],
        failed_segment_indexes=[index for index, _ in model_failures],
    )
    failure.segment_semantic_metrics = {
        **{
            index: extract.semantic_metrics
            for index, extract in enumerate(extracts)
            if extract is not None
        },
        **{index: exc.semantic_metrics for index, exc in model_failures},
    }
    return failure


def _compile_in_context(
    context: Context,
    compiler: IndexMetadataExtractor,
    document: SourceDocument,
    source_file: str,
    source_record: SourceRecord,
    max_tokens: int | None,
    execution: IngestExecutionPort | None,
) -> IndexExtractResult:
    if execution is not None:
        execution.before_model_call()
    return context.run(
        compiler.compile,
        document,
        source_file=source_file,
        source_record=source_record,
        max_tokens=max_tokens,
    )


def _index_metadata_extract_payload(document: SourceDocument, source_file: str, source_record: SourceRecord) -> dict[str, Any]:
    title = _document_title(document)
    return {
        "source": {
            "title": title,
            "source_path": source_file,
            "format": document.content.format,
            "language": _dominant_source_language(document),
        },
        "units": [_model_source_unit_payload(position, unit) for position, unit in enumerate(source_record.units)],
    }


def _model_source_unit_payload(position: int, unit: SourceRecordUnit) -> dict[str, object]:
    return {
        "position": position,
        "unit_id": unit.evidence.source_unit_id or f"U{unit.index}",
        "title": unit.title,
        "type": unit.unit_type,
        "language": _source_text_language(
            "\n".join(part for part in (unit.title or "", unit.evidence.excerpt) if part)
        ),
        "text": canonical_evidence_text(unit.evidence.excerpt),
    }


def _auto_source_record(document: SourceDocument, source_file: str) -> SourceRecord:
    title = _document_title(document)
    body = _document_body(document)
    record_id = f"auto:{content_hash(document.source_id, document.fingerprint.content_hash)}"
    units = _auto_source_record_units(document, source_file, record_id, title, body)
    return SourceRecord(
        record_id=record_id,
        source=KnowledgeSource(
            source_type=_knowledge_source_type(document),
            source_app=document.origin.connector or "auto",
            source_id=document.source_id,
            source_path=source_file,
            title=title,
            created_at=document.origin.created_at,
            updated_at=document.origin.updated_at,
        ),
        raw_source=source_file,
        content_hash=document.fingerprint.content_hash,
        source_focus=title,
        summary=f"Index metadata ingest audit record for {title}.",
        units=units,
        attachments=_source_record_attachments(document),
        contribution_map=[
            SourceRecordContribution(
                item_id="Q1",
                contribution=f"Indexed {title} through the raw-grounded ingest chain.",
                evidence_unit_ids=[f"U{unit.index}" for unit in units],
                status="accepted",
            )
        ],
    )


def _source_record_attachments(document: SourceDocument) -> list[SourceRecordAttachment]:
    attachments: list[SourceRecordAttachment] = []
    for index, payload in enumerate(document.content.attachments):
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        name = str(payload.get("name") or Path(str(payload.get("path") or payload.get("relative_path") or "")).name).strip()
        if not name:
            continue
        topic = str(payload.get("topic") or metadata.get("topic") or metadata.get("caption") or "").strip()
        description = str(
            payload.get("description") or metadata.get("description") or metadata.get("mineru_description") or metadata.get("caption") or ""
        ).strip()
        attachments.append(
            SourceRecordAttachment(
                attachment_id=str(payload.get("attachment_id") or payload.get("content_hash") or f"attachment:{index}"),
                attachment_type=_source_attachment_type(payload.get("attachment_type")),
                name=name,
                topic=topic,
                description=description,
                source_range=str(payload.get("source_range") or metadata.get("source_range") or ""),
                path=str(payload.get("path") or "") or None,
                relative_path=str(payload.get("relative_path") or "") or None,
                mime_type=str(payload.get("mime_type") or "") or None,
                content_hash=str(payload.get("content_hash") or "") or None,
                source=str(payload.get("source") or ""),
                metadata=dict(metadata),
            )
        )
    return attachments


def _source_attachment_type(value: object) -> str:
    attachment_type = str(value or "file").strip().casefold()
    return attachment_type if attachment_type in {"image", "file", "table", "other"} else "other"


def _auto_source_record_units(document: SourceDocument, source_file: str, record_id: str, title: str, body: str) -> list[SourceRecordUnit]:
    unitization = document.metadata.get("source_unitization") if isinstance(document.metadata, dict) else None
    raw_units = unitization.get("units") if isinstance(unitization, dict) else None
    units: list[SourceRecordUnit] = []
    if isinstance(raw_units, list):
        for raw in raw_units:
            if not isinstance(raw, dict):
                continue
            index = len(units)
            content = str(raw.get("content") or "").strip()
            if not content:
                continue
            excerpt = content or title
            evidence = KnowledgeEvidenceSpan(
                source_record_id=record_id,
                source_path=source_file,
                source_unit_index=index,
                excerpt=excerpt,
                excerpt_hash=content_hash(f"{source_file}:{raw.get('index') or index}", excerpt),
                char_start=0,
                char_end=len(content),
            )
            units.append(
                SourceRecordUnit(
                    index=index,
                    unit_type=_source_record_unit_type(str(raw.get("unit_type") or ""), document),
                    title=str(raw.get("title") or title).strip() or title,
                    summary=excerpt,
                    evidence=evidence,
                    metadata={
                        "ingest_profile": INGEST_PROFILE,
                        "content_format": document.content.format,
                        "source_unitization_rule": raw.get("rule"),
                        "source_range": raw.get("source_range"),
                        "structural_path": raw.get("structural_path"),
                    },
                )
            )
    if units:
        return units
    excerpt = body or title
    evidence = KnowledgeEvidenceSpan(
        source_record_id=record_id,
        source_path=source_file,
        source_unit_index=0,
        excerpt=excerpt,
        excerpt_hash=content_hash(source_file, excerpt),
        char_start=0,
        char_end=len(body),
    )
    return [
        SourceRecordUnit(
            index=0,
            unit_type="section" if document.content.format in {"markdown", "html"} else "note",
            title=title,
            summary=excerpt,
            evidence=evidence,
            metadata={"ingest_profile": INGEST_PROFILE, "content_format": document.content.format},
        )
    ]


def _source_record_unit_type(unit_type: str, document: SourceDocument):
    if unit_type in {"conversation_turn", "excerpt", "evidence"}:
        return unit_type
    if unit_type in {"section", "paragraph", "heading", "page", "table", "figure"} or document.content.format in {"markdown", "html"}:
        return "section"
    return "note"


def _document_title(document: SourceDocument) -> str:
    metadata_title = str(document.metadata.get("title") or document.metadata.get("display_name") or "").strip()
    if metadata_title:
        return inline_text(metadata_title)
    text = document.content.text or ""
    fallback = Path(document.origin.raw_path.replace("\\", "/")).stem or document.source_id
    return extract_heading(text, fallback)


def _knowledge_source_type(document: SourceDocument):
    if document.source_type in {"markdown", "excerpt", "document", "web"}:
        return document.source_type if document.source_type != "excerpt" else "manual"
    if document.source_type.endswith("_chat"):
        return "chat"
    if document.content.format == "html":
        return "html"
    if document.content.format == "markdown":
        return "markdown"
    return "text_note"


def _failed_source_result_from_resolver(failure: dict[str, object]) -> IngestSourceResult:
    ref = failure.get("ref")
    ref_payload = ref if isinstance(ref, dict) else {}
    connector = str(failure.get("connector") or "input_resolver")
    stage = str(failure.get("stage") or "input_resolution")
    return IngestSourceResult(
        connector=connector,
        source_id=str(ref_payload.get("source_id") or connector),
        source_file=str(ref_payload.get("uri") or connector),
        should_process=False,
        mode="failed",
        reason=f"{stage} failed.",
        status="failed",
        error_stage=stage,
        error_code=str(failure.get("error_code") or "KA-INGEST-INPUT"),
        error_category=str(failure.get("error_category") or "input"),
        error_retryable=bool(failure.get("error_retryable", False)),
        error_hint=str(failure.get("error_hint") or "Resolve the source error and submit a new input generation."),
        error_type=str(failure.get("error_type") or "InputResolutionError"),
        error_message=str(failure.get("error_message") or failure.get("message") or "Input resolution failed."),
        ingest_profile=INGEST_PROFILE,
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


def _auto_metrics(elapsed_seconds: float) -> dict[str, object]:
    return {"elapsed_seconds": elapsed_seconds, "semantic": _empty_semantic_metrics()}


def _empty_semantic_metrics() -> dict[str, object]:
    return {
        "semantic_call_count": 0,
        "prompt_tokens": 0,
        "prompt_cached_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "prompt_stable_chars": 0,
        "prompt_dynamic_chars": 0,
        "dynamic_to_stable_ratio": None,
        "completion_tokens": 0,
        "total_tokens": 0,
        "elapsed_seconds": 0.0,
        "tokens_per_second": None,
        "prompt_cache_rate": None,
        "by_contract": [],
        "calls": [],
    }


def _dedupe_pages(pages: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for page in pages:
        if page and page not in seen:
            seen.add(page)
            result.append(page)
    return result


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
