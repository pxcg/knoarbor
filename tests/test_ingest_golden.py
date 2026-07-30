from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import IngestSegmentationConfig
from knoarbor.pipelines.source_segmentation import SourceSegmentBatch, SourceSegmenter

from tests.harness.ingest_cases import codex_chat_source_document, long_markdown_source_document
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


def segmentation_config() -> IngestSegmentationConfig:
    return IngestSegmentationConfig(
        enabled=True,
        soft_chars_per_segment=1200,
        max_chars_per_segment=2200,
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


if __name__ == "__main__":
    unittest.main()
