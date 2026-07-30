from __future__ import annotations

import json
import unittest

from knoarbor.core.config import IngestSegmentationConfig
from knoarbor.core.schemas.ingest_run import build_excerpt_source_document
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.pipelines.source_segmentation import SourceSegmenter
from knoarbor.core.source_unitization import SourceUnitizer, attach_source_unitization


class SourceUnitizationTests(unittest.TestCase):
    def test_short_markdown_can_be_one_segment_and_multiple_source_units(self) -> None:
        document = make_document(
            source_type="markdown",
            text="# A2A\n\nProtocol overview.\n\n## Agent Card\n\nCapability metadata.\n\n## Task\n\nTask lifecycle.",
        )

        segment_batch = SourceSegmenter(IngestSegmentationConfig(max_chars_per_segment=18000)).segment(document)
        unitization = SourceUnitizer().unitize(segment_batch.segments[0].document)

        self.assertEqual(len(segment_batch.segments), 1)
        self.assertTrue(segment_batch.segments[0].is_full_source)
        self.assertEqual(unitization.rule, "markdown_heading")
        self.assertEqual([unit.title for unit in unitization.units], ["A2A", "Agent Card", "Task"])

    def test_heading_only_parent_is_structural_path_not_evidence_unit(self) -> None:
        document = make_document(
            source_type="markdown",
            text="## 协作模式\n\n### 主从式协作\n\nMaster controls workers.\n\n### 对等式协作\n\nPeers coordinate.",
        )

        unitization = SourceUnitizer().unitize(document)

        self.assertEqual([unit.title for unit in unitization.units], ["主从式协作", "对等式协作"])
        self.assertEqual(unitization.units[0].structural_path, ["协作模式", "主从式协作"])
        self.assertTrue(unitization.units[0].content.startswith("## 协作模式\n\n### 主从式协作"))
        self.assertNotIn("## 协作模式", unitization.units[1].content)

    def test_heading_only_sibling_is_not_attached_to_next_section(self) -> None:
        document = make_document(
            source_type="markdown",
            text="## Empty sibling\n\n## Populated sibling\n\nSupported evidence.",
        )

        unitization = SourceUnitizer().unitize(document)

        self.assertEqual([unit.title for unit in unitization.units], ["Populated sibling"])
        self.assertEqual(unitization.units[0].content, "## Populated sibling\n\nSupported evidence.")

    def test_ordinal_only_heading_is_coalesced_with_same_level_title(self) -> None:
        document = make_document(
            source_type="markdown",
            text=(
                "# 1.\n\n"
                "# Change and inequality in healthy longevity\n\n"
                "Supported evidence.\n\n"
                "## 1.1 Global trends\n\n"
                "More evidence."
            ),
        )

        unitization = SourceUnitizer().unitize(document)

        self.assertEqual(
            [unit.title for unit in unitization.units],
            [
                "1. Change and inequality in healthy longevity",
                "1.1 Global trends",
            ],
        )
        self.assertEqual(
            unitization.units[0].structural_path,
            ["1. Change and inequality in healthy longevity"],
        )
        self.assertTrue(unitization.units[0].content.startswith("# 1."))

    def test_chat_unitization_preserves_complete_turn_groups(self) -> None:
        payload = {
            "session_id": "s1",
            "turns": [
                {"raw_index": 0, "role": "system", "content": "internal"},
                {"raw_index": 1, "role": "user", "content": "What is an agent loop?"},
                {"raw_index": 2, "role": "assistant", "content": "An agent loop alternates reasoning and tools."},
                {"raw_index": 3, "role": "tool", "content": "{\"noise\": true}"},
                {"raw_index": 4, "role": "user", "content": "How does memory fit?"},
                {"raw_index": 5, "role": "assistant", "content": "Memory keeps short and long term context."},
            ],
        }
        document = make_document(source_type="codex_chat", text=json.dumps(payload, ensure_ascii=False), fmt="json")

        unitization = SourceUnitizer().unitize(document)

        self.assertEqual(unitization.rule, "agent_task_turn_group")
        self.assertEqual(len(unitization.units), 2)
        self.assertEqual(unitization.units[0].raw_indexes, [1, 2])
        self.assertEqual(unitization.units[1].raw_indexes, [4, 5])
        self.assertIn("What is an agent loop?", unitization.units[0].content)
        self.assertNotIn("internal", unitization.units[0].content)
        self.assertNotIn("noise", "\n".join(unit.content for unit in unitization.units))

    def test_attach_source_unitization_persists_deterministic_units(self) -> None:
        document = attach_source_unitization(
            make_document(
                source_type="markdown",
                text="# A2A\n\nProtocol overview.\n\n## Agent Card\n\nCapability metadata.",
                attachments=[{"name": "figure-1.png", "relative_path": "images/figure-1.png"}],
            )
        )
        unitization = document.metadata["source_unitization"]

        self.assertEqual([unit["title"] for unit in unitization["units"]], ["A2A", "Agent Card"])
        self.assertEqual(unitization["units"][0]["rule"], "markdown_heading")
        self.assertEqual(document.content.attachments[0]["name"], "figure-1.png")

    def test_public_summary_omits_unit_content(self) -> None:
        unitization = SourceUnitizer().unitize(
            make_document(
                source_type="markdown",
                text="# API\n\nsecret-token-should-not-be-logged\n\n## Params\n\nVisible title only.",
            )
        )

        summary = unitization.public_summary()
        dumped = json.dumps(summary, ensure_ascii=False)

        self.assertIn("content_chars", dumped)
        self.assertNotIn("content\":", dumped)
        self.assertNotIn("secret-token-should-not-be-logged", dumped)

    def test_source_unit_title_preserves_complete_semantic_text(self) -> None:
        sentence = "完整语义标题" * 30
        unitization = SourceUnitizer().unitize(make_document(source_type="excerpt", text=sentence))

        self.assertEqual(unitization.units[0].title, sentence)

    def test_selected_excerpt_uses_explicit_title_and_unwrapped_evidence(self) -> None:
        document = build_excerpt_source_document(text="北极光来自高层大气发光。", title="北极光摘要")

        unitization = SourceUnitizer().unitize(document)

        self.assertEqual(unitization.units[0].title, "北极光摘要")
        self.assertEqual(unitization.units[0].content, "北极光来自高层大气发光。")
        self.assertEqual(unitization.units[0].structural_path, ["北极光摘要"])

    def test_knoarbor_chat_prefers_normalized_messages_over_aggregate_turns(self) -> None:
        payload = {
            "messages": [
                {"raw_index": 0, "role": "user", "content": "北极光如何形成？"},
                {"raw_index": 1, "role": "assistant", "content": "带电粒子与高层大气碰撞发光。"},
            ],
            "turns": [
                {"index": 0, "user": "北极光如何形成？", "assistant": "带电粒子与高层大气碰撞发光。"},
            ],
        }
        document = make_document(source_type="knoarbor_chat", text=json.dumps(payload, ensure_ascii=False), fmt="json")

        unitization = SourceUnitizer().unitize(document)

        self.assertEqual(unitization.rule, "chat_turn_group")
        self.assertEqual(len(unitization.units), 1)
        self.assertEqual(unitization.units[0].title, "北极光如何形成？")
        self.assertEqual(unitization.units[0].raw_indexes, [0, 1])
        self.assertNotIn('"messages"', unitization.units[0].content)

    def test_parsed_document_sections_become_source_units(self) -> None:
        document = SourceDocument(
            source_id="doc-1",
            source_type="document",
            origin=SourceOrigin(connector="document", uri="file:///doc.pdf", raw_path="raw/inbox/documents/doc.md"),
            content=SourceContent(
                format="markdown",
                text="# Parsed\n\nBody",
                sections=[
                    {"title": "Page 1", "text": "Intro evidence.", "page_number": 1},
                    {"title": "Table 1", "content": "| A | B |\n|---|---|\n| 1 | 2 |", "type": "table"},
                ],
            ),
            metadata={"title": "Parsed Doc"},
            fingerprint=SourceFingerprint(content_hash="abc", connector_version="document@1"),
        )

        unitization = SourceUnitizer().unitize(document)

        self.assertEqual(unitization.rule, "parsed_document_structure")
        self.assertEqual(len(unitization.units), 2)
        self.assertEqual(unitization.units[0].metadata["page_number"], 1)
        self.assertEqual(unitization.units[1].metadata["type"], "table")


def make_document(*, source_type: str, text: str, fmt: str = "markdown", attachments: list[dict[str, object]] | None = None) -> SourceDocument:
    return SourceDocument(
        source_id="source-1",
        source_type=source_type,  # type: ignore[arg-type]
        origin=SourceOrigin(connector="test", uri="test://source", raw_path="raw/inbox/notes/source.md"),
        content=SourceContent(format=fmt, text=text, attachments=attachments or []),  # type: ignore[arg-type]
        metadata={"title": "Source"},
        fingerprint=SourceFingerprint(content_hash="abc123", connector_version="test@1"),
    )


if __name__ == "__main__":
    unittest.main()
