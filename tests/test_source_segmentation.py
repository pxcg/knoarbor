from __future__ import annotations

import json
import unittest

from knoarbor.core.config import IngestSegmentationConfig
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.pipelines.source_segmentation import SourceSegmenter


class SourceSegmentationTests(unittest.TestCase):
    def test_markdown_uses_heading_blocks(self) -> None:
        document = make_document(
            source_type="markdown",
            text="# Intro\n\n" + "a" * 900 + "\n\n## Architecture\n\n" + "b" * 900 + "\n\n## Usage\n\n" + "c" * 900,
        )

        batch = SourceSegmenter(test_config()).segment(document)

        self.assertEqual(batch.segmentation_mode, "heading")
        self.assertGreaterEqual(len(batch.segments), 2)
        self.assertTrue(all(segment.document.metadata["segmentation"]["enabled"] for segment in batch.segments))

    def test_chat_keeps_user_assistant_turn_groups_together(self) -> None:
        payload = {
            "session_id": "s1",
            "turns": [
                {"raw_index": 0, "role": "user", "content": "question " + "a" * 20},
                {"raw_index": 1, "role": "assistant", "content": "answer " + "b" * 1500},
                {"raw_index": 2, "role": "user", "content": "next " + "c" * 20},
                {"raw_index": 3, "role": "assistant", "content": "reply " + "d" * 1500},
            ],
        }
        document = make_document(source_type="codex_chat", text=json.dumps(payload, ensure_ascii=False), fmt="json")

        batch = SourceSegmenter(test_config()).segment(document)

        self.assertEqual(batch.segmentation_mode, "turns")
        self.assertEqual(len(batch.segments), 2)
        first_payload = json.loads(batch.segments[0].document.content.text)
        self.assertEqual([turn["raw_index"] for turn in first_payload["turns"]], [0, 1])
        self.assertEqual(batch.segments[1].source_range.from_index, 2)
        self.assertEqual(batch.segments[1].source_range.to_index, 3)

    def test_claude_code_chat_uses_turn_segmentation(self) -> None:
        payload = {
            "session_id": "s1",
            "turns": [
                {"raw_index": 0, "role": "user", "content": "question " + "a" * 20},
                {"raw_index": 1, "role": "assistant", "content": "answer " + "b" * 1500},
                {"raw_index": 2, "role": "user", "content": "next " + "c" * 20},
                {"raw_index": 3, "role": "assistant", "content": "reply " + "d" * 1500},
            ],
        }
        document = make_document(source_type="claude_code_chat", text=json.dumps(payload, ensure_ascii=False), fmt="json")

        batch = SourceSegmenter(test_config()).segment(document)

        self.assertEqual(batch.segmentation_mode, "turns")
        self.assertEqual(len(batch.segments), 2)

    def test_short_source_returns_single_full_segment(self) -> None:
        document = make_document(source_type="text", text="short note")

        batch = SourceSegmenter(test_config()).segment(document)

        self.assertEqual(batch.segmentation_mode, "none")
        self.assertEqual(len(batch.segments), 1)
        self.assertTrue(batch.segments[0].is_full_source)

    def test_oversized_markdown_heading_block_records_hard_split_warning(self) -> None:
        document = make_document(
            source_type="markdown",
            text="# Large\n\n" + "a" * 4500 + "\n\n## Next\n\n" + "b" * 900,
        )

        batch = SourceSegmenter(test_config()).segment(document)

        warnings = [warning for segment in batch.segments for warning in segment.warnings]
        self.assertEqual(batch.segmentation_mode, "heading")
        self.assertTrue(any(warning.startswith("hard_split:heading:Large") for warning in warnings))
        self.assertGreater(len(batch.segments), 1)


def test_config() -> IngestSegmentationConfig:
    return IngestSegmentationConfig(
        enabled=True,
        soft_chars_per_segment=1000,
        max_chars_per_segment=2000,
        overlap_chars=10,
        max_segments_per_source=10,
        min_segment_chars=10,
    )


def make_document(*, source_type: str, text: str, fmt: str = "markdown") -> SourceDocument:
    return SourceDocument(
        source_id="source-1",
        source_type=source_type,  # type: ignore[arg-type]
        origin=SourceOrigin(connector="test", uri="test://source", raw_path="raw/notes/source.md"),
        content=SourceContent(format=fmt, text=text),  # type: ignore[arg-type]
        metadata={"title": "Source"},
        fingerprint=SourceFingerprint(content_hash="abc123", connector_version="test@1"),
    )


if __name__ == "__main__":
    unittest.main()
