from __future__ import annotations

import unittest

from pydantic import ValidationError

from knoarbor.core.schemas.chat import ChatAnswerDecision
from knoarbor.services.chat_support_spans import build_support_spans, support_span_catalog


class ChatSupportSpanTests(unittest.TestCase):
    def test_decision_schema_rejects_removed_quote_contract(self) -> None:
        with self.assertRaises(ValidationError):
            ChatAnswerDecision.model_validate(
                {
                    "mode": "raw",
                    "spans": ["sp_1_1"],
                    "visuals": [],
                    "gap": None,
                    "generate_image": False,
                    "dimension_coverage": [
                        {
                            "dimension_id": "d1",
                            "coverage_kind": "direct",
                            "support_span_ids": ["sp_1_1"],
                            "answer_markdown": "Answer.",
                            "evidence_quotes": [{"evidence_id": "ev_1", "quote": "legacy"}],
                        }
                    ],
                }
            )

    def test_builds_deterministic_sentence_and_structural_spans(self) -> None:
        content = "Overview sentence one. Sentence two!\n- Atomic list item\n## Heading"
        item = {
            "evidence_id": "ev_1",
            "content": content,
            "source_unit_char_start": 100,
            "source_unit_id": "unit_1",
            "raw_revision_id": "rawrev_1",
            "source_path": "sources/demo.md",
            "title": "Demo",
        }

        spans = build_support_spans(item, evidence_index=2)

        self.assertEqual([span.support_span_id for span in spans], ["sp_3_1", "sp_3_2", "sp_3_3", "sp_3_4"])
        self.assertEqual(
            [span.text for span in spans],
            ["Overview sentence one.", "Sentence two!", "- Atomic list item", "## Heading"],
        )
        for span in spans:
            local_start = span.char_start - 100
            local_end = span.char_end - 100
            self.assertEqual(content[local_start:local_end], span.text)

    def test_catalog_ids_are_stable_and_scoped_by_evidence_order(self) -> None:
        evidence = [
            {"evidence_id": "ev_a", "content": "Alpha。Beta。", "source_unit_char_start": 10},
            {"evidence_id": "ev_b", "content": "- Gamma", "source_unit_char_start": 50},
        ]

        first = support_span_catalog(evidence)
        second = support_span_catalog(evidence)

        self.assertEqual(first, second)
        self.assertEqual([span.support_span_id for span in first], ["sp_1_1", "sp_1_2", "sp_2_1"])
        self.assertEqual([(span.char_start, span.char_end) for span in first], [(10, 16), (16, 21), (50, 57)])

    def test_citation_uses_selected_support_span_not_retrieval_locator(self) -> None:
        item = {
            "evidence_id": "ev_1",
            "content": "First sentence. Selected sentence.",
            "source_unit_char_start": 200,
            "char_start": 200,
            "char_end": 235,
            "source_unit_id": "unit_1",
            "raw_revision_id": "rawrev_1",
            "source_path": "sources/demo.md",
        }

        selected = build_support_spans(item, evidence_index=0)[1]
        citation = selected.citation()

        self.assertEqual((citation.char_start, citation.char_end), (216, 234))
        self.assertNotEqual((citation.char_start, citation.char_end), (item["char_start"], item["char_end"]))
        self.assertEqual(item["content"][citation.char_start - 200:citation.char_end - 200], "Selected sentence.")


if __name__ == "__main__":
    unittest.main()
