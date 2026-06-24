from __future__ import annotations

import json
import unittest

from knoarbor.core.config import IngestSegmentationConfig
from knoarbor.core.schemas.knowledge_extract import CompileContext, ContentUnit, KnowledgeExtract, KnowledgeSource
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.pipelines.source_segmentation import SourceSegmenter
from knoarbor.core.source_unitization import SourceUnitizer, apply_source_units_to_extract, attach_source_unitization


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

    def test_apply_source_units_overrides_model_unit_boundaries(self) -> None:
        document = attach_source_unitization(
            make_document(
                source_type="markdown",
                text="# A2A\n\nProtocol overview.\n\n## Agent Card\n\nCapability metadata.",
            )
        )
        model_extract = KnowledgeExtract(
            source=KnowledgeSource(source_type="markdown", source_app="markdown", source_id="source-1", source_path="raw/notes/source.md", title="A2A"),
            content_units=[
                ContentUnit(index=0, unit_type="note", role="note", title="Model Unit", content=document.content.text),
            ],
            compile_context=CompileContext(primary_content=document.content.text, latest_unit_indexes=[0]),
            warnings=["model_warning"],
        )

        extract = apply_source_units_to_extract(document, model_extract)

        self.assertEqual([unit.title for unit in extract.content_units], ["A2A", "Agent Card"])
        self.assertEqual(extract.compile_context.latest_unit_indexes, [0, 1])
        self.assertIn("model_warning", extract.warnings)
        self.assertEqual(extract.content_units[0].metadata["source_unitization_rule"], "markdown_heading")

    def test_parsed_document_sections_become_source_units(self) -> None:
        document = SourceDocument(
            source_id="doc-1",
            source_type="document",
            origin=SourceOrigin(connector="document", uri="file:///doc.pdf", raw_path="raw/documents/doc.md"),
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
