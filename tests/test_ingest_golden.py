from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.audit.ingest_report import build_ingest_run_record, render_ingest_report
from knoarbor.core.config import IngestSegmentationConfig, PrivacyConfig
from knoarbor.core.markdown import parse_frontmatter
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.schemas.ingest_pipeline import IngestPipelineResult
from knoarbor.pipelines.ingest import IngestPipeline
from knoarbor.pipelines.source_segmentation import SourceSegmentBatch, SourceSegmenter

from tests.harness.ingest_cases import (
    MultiObjectSegmentWorkflow,
    SourceDigestOnlyWorkflow,
    codex_chat_source_document,
    long_markdown_source_document,
)
from tests.harness.snapshot import assert_json_snapshot


FIXTURE_DIR = Path(__file__).resolve().parent / "harness" / "fixtures" / "ingest"


class IngestGoldenTests(unittest.TestCase):
    def test_source_segmentation_matches_golden_fixture(self) -> None:
        segmenter = SourceSegmenter(segmentation_config())
        snapshot = {
            "markdown": _segment_batch_snapshot(segmenter.segment(long_markdown_source_document())),
            "codex_chat": _segment_batch_snapshot(segmenter.segment(codex_chat_source_document())),
        }
        assert_json_snapshot(self, snapshot, FIXTURE_DIR / "source_segmentation.json")

    def test_segmented_ingest_aggregation_matches_golden_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "wiki"
            vault.mkdir()
            workflow = SourceDigestOnlyWorkflow()
            result = IngestPipeline(workflow).run_document(  # type: ignore[arg-type]
                long_markdown_source_document(),
                vault_path=vault,
                privacy_config=PrivacyConfig(),
                write=True,
                max_tokens=None,
                auto_scoped_lint=False,
                segmentation_config=segmentation_config(),
                write_report=False,
                append_ledger=False,
            )

        run_result = IngestPipelineResult(
            results=[result],
            stats={
                "source_count": 1,
                "processed_count": 1,
                "skipped_count": 0,
                "failed_count": 0,
                "written_count": len(result.generated_pages),
                "segment_count": len(result.segments),
                "processed_segment_count": sum(1 for segment in result.segments if segment.get("status") in {"processed", "written"}),
                "failed_segment_count": sum(1 for segment in result.segments if segment.get("status") == "failed"),
                "max_segment_chars": max(int(segment.get("chars") or 0) for segment in result.segments),
            },
        )
        run_result.metrics = {"elapsed_seconds": 0.0, "semantic": {"semantic_call_count": workflow.calls, "total_tokens": 0}}
        record = build_ingest_run_record(
            run_result,
            run_id="golden-ingest-run",
            started_at="2026-01-01 00:00:00",
            finished_at="2026-01-01 00:00:01",
        )
        record["quality_trend"] = {}
        snapshot = {
            "source": _stable_source_result(result),
            "report": _normalize_report(render_ingest_report(record)),
        }
        assert_json_snapshot(self, snapshot, FIXTURE_DIR / "segmented_ingest_aggregation.json")

    def test_long_markdown_quality_dataset_matches_golden_fixture(self) -> None:
        snapshot = _segmented_quality_snapshot(long_markdown_source_document())
        assert_json_snapshot(self, snapshot, FIXTURE_DIR / "long_markdown_quality.json")

    def test_codex_chat_quality_dataset_matches_golden_fixture(self) -> None:
        snapshot = _segmented_quality_snapshot(codex_chat_source_document())
        assert_json_snapshot(self, snapshot, FIXTURE_DIR / "codex_chat_quality.json")


def segmentation_config() -> IngestSegmentationConfig:
    return IngestSegmentationConfig(
        enabled=True,
        soft_chars_per_segment=1200,
        max_chars_per_segment=2200,
        overlap_chars=80,
        max_segments_per_source=10,
        min_segment_chars=300,
    )


def _segment_batch_snapshot(batch: SourceSegmentBatch) -> dict[str, object]:
    return {
        "source_id": batch.source_id,
        "source_file": batch.source_file,
        "segmentation_mode": batch.segmentation_mode,
        "summary": batch.summary(),
        "warnings": batch.warnings,
        "segments": [
            {
                "segment_id": segment.segment_id,
                "index": segment.index,
                "title": segment.title,
                "chars": len(segment.content),
                "source_range": segment.source_range.model_dump(),
                "context_before_chars": len(segment.context_before),
                "context_after_chars": len(segment.context_after),
                "is_full_source": segment.is_full_source,
                "content_format": segment.document.content.format,
                "metadata_segmentation": segment.document.metadata.get("segmentation"),
                "warnings": segment.warnings,
            }
            for segment in batch.segments
        ],
    }


def _stable_source_result(result: Any) -> dict[str, object]:
    return {
        "connector": result.connector,
        "source_id": result.source_id,
        "source_file": result.source_file,
        "status": result.status,
        "wrote": result.wrote,
        "generated_pages": result.generated_pages,
        "approved_operation_indexes": result.approved_operation_indexes,
        "segmentation": result.segmentation,
        "quality_gate": result.quality_gate,
        "context": {
            "write_policy": result.context.get("write_policy"),
            "semantic_metrics": _stable_semantic_metrics(result.context.get("semantic_metrics")),
        },
        "segments": [
            {
                "index": segment.get("index"),
                "title": segment.get("title"),
                "chars": segment.get("chars"),
                "source_range": segment.get("source_range"),
                "is_full_source": segment.get("is_full_source"),
                "status": segment.get("status"),
                "approved_operation_indexes": segment.get("approved_operation_indexes"),
                "generated_pages": segment.get("generated_pages"),
                "warnings": segment.get("warnings"),
                "relation_operations": segment.get("relation_operations"),
                "metrics": {
                    "semantic": _stable_semantic_metrics(dict(segment.get("metrics") or {}).get("semantic")),
                },
            }
            for segment in result.segments
        ],
    }


def _segmented_quality_snapshot(document: SourceDocument) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        vault = Path(tmp_dir) / "wiki"
        vault.mkdir()
        workflow = MultiObjectSegmentWorkflow()
        result = IngestPipeline(workflow).run_document(  # type: ignore[arg-type]
            document,
            vault_path=vault,
            privacy_config=PrivacyConfig(),
            write=True,
            max_tokens=None,
            auto_scoped_lint=False,
            segmentation_config=segmentation_config(),
            write_report=False,
            append_ledger=False,
        )
        run_result = IngestPipelineResult(
            results=[result],
            stats={
                "source_count": 1,
                "processed_count": 1 if result.status != "failed" else 0,
                "skipped_count": 1 if result.status == "skipped" else 0,
                "failed_count": 1 if result.status == "failed" else 0,
                "written_count": len(result.generated_pages),
                "segment_count": len(result.segments),
                "processed_segment_count": sum(1 for segment in result.segments if segment.get("status") in {"processed", "written"}),
                "failed_segment_count": sum(1 for segment in result.segments if segment.get("status") == "failed"),
                "max_segment_chars": max(int(segment.get("chars") or 0) for segment in result.segments),
            },
        )
        run_result.metrics = {"elapsed_seconds": 0.0, "semantic": {"semantic_call_count": workflow.calls, "total_tokens": 0}}
        record = build_ingest_run_record(
            run_result,
            run_id="golden-quality-ingest-run",
            started_at="2026-01-01 00:00:00",
            finished_at="2026-01-01 00:00:01",
        )
        record["quality_trend"] = {}
        page_snapshots = _written_page_snapshots(vault, result.generated_pages)

    return {
        "source": _stable_source_result(result),
        "written_pages": page_snapshots,
        "report": _normalize_report(render_ingest_report(record)),
    }


def _written_page_snapshots(vault: Path, pages: list[str]) -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    for page in pages:
        content = (vault / page).read_text(encoding="utf-8")
        metadata = parse_frontmatter(content)
        title_match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
        snapshots.append(
            {
                "path": page,
                "title": title_match.group(1).strip() if title_match else "",
                "type": metadata.get("type"),
                "source": metadata.get("source"),
                "tags": metadata.get("tags", []),
                "wikilinks": sorted(set(re.findall(r"\[\[([^\]|]+)", content))),
            }
        )
    return snapshots


def _stable_semantic_metrics(value: object) -> dict[str, object]:
    metrics = dict(value or {}) if isinstance(value, dict) else {}
    return {
        "semantic_call_count": metrics.get("semantic_call_count", 0),
        "prompt_tokens": metrics.get("prompt_tokens", 0),
        "completion_tokens": metrics.get("completion_tokens", 0),
        "total_tokens": metrics.get("total_tokens", 0),
    }


def _normalize_report(report: str) -> str:
    report = re.sub(r"- elapsed_seconds: .+", "- elapsed_seconds: <elapsed>", report)
    report = re.sub(r"- tokens_per_second: .+", "- tokens_per_second: <tokens_per_second>", report)
    report = re.sub(r"elapsed: [0-9.]+s", "elapsed: <elapsed>s", report)
    return report


if __name__ == "__main__":
    unittest.main()
