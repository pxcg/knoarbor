from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteItem, WikiDraftInput
from knoarbor.pipelines.ingest_write_policy import IngestWritePolicy


class IngestWritePolicyTests(unittest.TestCase):
    def test_write_policy_rejects_duplicate_source_digest_creates(self) -> None:
        items = [
            _write_item("Source A", "sources"),
            _write_item("Source B", "sources"),
        ]

        with self.assertRaisesRegex(ValueError, "multiple source digest creates"):
            IngestWritePolicy().apply(items)

    def test_write_policy_keeps_valid_write_items_unchanged(self) -> None:
        items = [
            _write_item("Agent Source", "sources"),
            _write_item("Agent Loop", "pages"),
        ]

        result = IngestWritePolicy().apply(items)

        self.assertEqual(result.items, items)
        self.assertEqual(result.changes, [])


def _write_item(title: str, page_dir: str) -> WikiDraftBatchWriteItem:
    return WikiDraftBatchWriteItem(
        source_file="raw/notes/source.md",
        wiki_draft=WikiDraftInput(
            title=title,
            page_dir=page_dir,
            question=title,
            answer=f"{title} answer.",
            summary=f"{title} summary.",
            claims=[f"C1: [[{title}]] is supported by the source."],
            entities=[f"[[{title}]]"],
            relations=[f"[[{title}]] | supported_by | [[Source]] | C1"],
            evidence=["C1 | raw/notes/source.md | section:test | source supports the claim | high"],
            synthesis=f"{title} synthesis.",
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        ),
    )


if __name__ == "__main__":
    unittest.main()
