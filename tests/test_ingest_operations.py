from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from knoarbor.core.config import IngestSegmentationConfig, PrivacyConfig
from knoarbor.core.schemas.ingest_pipeline import IngestSourceResult
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.pipelines.ingest_auto import (
    AutoIngestPipeline,
    IndexExtractResult,
    _auto_source_record,
    _compile_segment_batch,
    _source_records_for_segment_batch,
)
from knoarbor.pipelines.source_segmentation import SourceSegmenter
from knoarbor.runtime.provider_control import impose_provider_cooldown, provider_cooldown_until
from knoarbor.runtime.provider_permits import ProviderPermitPool


class IngestOperationsTests(unittest.TestCase):
    def test_ready_sources_execute_concurrently_and_keep_input_order(self) -> None:
        documents = [_document("# One"), _document("# Two"), _document("# Three")]
        documents = [
            document.model_copy(
                update={
                    "source_id": f"source-{index}",
                    "origin": document.origin.model_copy(update={"raw_path": f"raw/source-{index}.md"}),
                }
            )
            for index, document in enumerate(documents)
        ]
        active = 0
        peak = 0
        lock = threading.Lock()

        def run_document(document, **_kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return IngestSourceResult(
                connector="test",
                source_id=document.source_id,
                source_file=document.origin.raw_path,
                should_process=True,
                mode="snapshot",
                reason="test",
            )

        pipeline = AutoIngestPipeline()
        with patch.object(pipeline, "run_document", side_effect=run_document):
            result = pipeline.run_generation(
                documents,
                resolver_failures=[],
                vault_path=Path("."),
                write=False,
                privacy_config=PrivacyConfig(),
                segmentation_config=IngestSegmentationConfig(),
                max_concurrent_segments=20,
                initial_concurrent_segments=2,
                write_report=False,
                append_ledger=False,
                max_tokens=400,
            )

        self.assertGreaterEqual(peak, 2)
        self.assertEqual([item.source_id for item in result.results], ["source-0", "source-1", "source-2"])

    def test_source_retry_recomputes_segments_without_a_second_persistent_lifecycle(self) -> None:
        document = _document("# One\n\n" + "a" * 2100 + "\n\n# Two\n\n" + "b" * 2100)
        batch = SourceSegmenter(
            IngestSegmentationConfig(max_chars_per_segment=2000, soft_chars_per_segment=1800, min_segment_chars=0)
        ).segment(document)
        base_record = _auto_source_record(document, "raw/source.md")
        segment_records, merged_record = _source_records_for_segment_batch(batch, base_record, "raw/source.md")
        compiler = _FailSecondSegmentOnceCompiler()
        kwargs = {
            "source_file": "raw/source.md",
            "source_record": merged_record,
            "max_tokens": 400,
        }

        with self.assertRaisesRegex(RuntimeError, "second segment"):
            _compile_segment_batch(compiler, batch, segment_records, **kwargs)
        _compile_segment_batch(compiler, batch, segment_records, **kwargs)

        self.assertEqual(compiler.calls, len(batch.segments) + 2)

    def test_parallel_segment_failure_waits_for_all_finite_calls(self) -> None:
        document = _document("# One\n\n" + "a" * 2100 + "\n\n# Two\n\n" + "b" * 2100)
        batch = SourceSegmenter(
            IngestSegmentationConfig(max_chars_per_segment=2000, soft_chars_per_segment=1800, min_segment_chars=0)
        ).segment(document)
        base_record = _auto_source_record(document, "raw/source.md")
        segment_records, merged_record = _source_records_for_segment_batch(batch, base_record, "raw/source.md")
        compiler = _FailFirstSegmentCompiler()

        with self.assertRaisesRegex(RuntimeError, "first segment"):
            _compile_segment_batch(
                compiler,
                batch,
                segment_records,
                source_file="raw/source.md",
                source_record=merged_record,
                max_tokens=400,
                max_concurrent_segments=len(batch.segments),
                initial_concurrent_segments=len(batch.segments),
            )

        self.assertEqual(compiler.calls, len(batch.segments))

    def test_provider_permit_honors_durable_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            with patch.dict("os.environ", {"KNOARBOR_RUNTIME_DIR": str(vault / "runtime")}):
                deadline = impose_provider_cooldown("provider:model:endpoint", seconds=0.25)
                self.assertGreaterEqual(deadline, provider_cooldown_until("provider:model:endpoint"))
                started = time.monotonic()
                with ProviderPermitPool().acquire("provider:model:endpoint", limit=1, vault_path=vault):
                    elapsed = time.monotonic() - started

            self.assertGreaterEqual(elapsed, 0.2)

    def test_idle_provider_adopts_next_attempts_derived_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pool = ProviderPermitPool()
            with pool.reserve_attempt("provider:model:endpoint", limit=1, vault_path=vault) as first:
                self.assertEqual(first.request_limit, 1)
            with pool.reserve_attempt("provider:model:endpoint", limit=3, vault_path=vault) as second:
                self.assertEqual(second.request_limit, 3)

    def test_provider_cooldown_is_shared_across_vaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with patch.dict("os.environ", {"KNOARBOR_RUNTIME_DIR": str(root / "runtime")}):
                impose_provider_cooldown("provider:model:endpoint", seconds=0.2)
                started = time.monotonic()
                with ProviderPermitPool().acquire("provider:model:endpoint", limit=1, vault_path=root / "second"):
                    elapsed = time.monotonic() - started

            self.assertGreaterEqual(elapsed, 0.15)


class _SegmentCompiler:
    def __init__(self) -> None:
        self.calls = 0

    def _result(self, source_record) -> IndexExtractResult:
        return IndexExtractResult(
            KnowledgeAtomBatch(source_record_id=source_record.record_id),
            "checkpoint synthesis",
            [],
            {"semantic_call_count": 1},
        )


class _FailSecondSegmentOnceCompiler(_SegmentCompiler):
    def compile(self, *_args: object, **kwargs: object) -> IndexExtractResult:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("second segment failed")
        return self._result(kwargs["source_record"])


class _FailFirstSegmentCompiler(_SegmentCompiler):
    def compile(self, *_args: object, **kwargs: object) -> IndexExtractResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("first segment failed")
        return self._result(kwargs["source_record"])


def _document(text: str) -> SourceDocument:
    return SourceDocument(
        source_id="source-1",
        source_type="markdown",
        origin=SourceOrigin(connector="test", uri="file:///source.md", raw_path="raw/source.md"),
        content=SourceContent(format="markdown", text=text),
        fingerprint=SourceFingerprint(content_hash="sha256:test", connector_version="test"),
    )
