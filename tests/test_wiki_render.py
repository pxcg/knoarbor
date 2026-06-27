from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.wiki_write import WikiDraft, WikiPatchInput
from knoarbor.semantic.wiki_render import apply_patched_markdown, render_markdown


class WikiRenderTests(unittest.TestCase):
    def test_render_markdown_creates_standard_sections(self) -> None:
        draft = WikiDraft(
            title="Agent Loop",
            page_dir="pages",
            question="Agent loop",
            summary="Agent loop is a control pattern.",
            claims=["C1: [[Agent Loop]] repeats observe, decide, act, and feedback."],
            entities=["[[Agent Loop]]"],
            relations=["[[Agent Loop]] | repeats | [[Control Cycle]] | C1"],
            evidence=["C1 | raw/inbox/notes/agent.md | section:Agent Loop | source states the loop steps | high"],
            synthesis="Agent loop repeats observe, decide, act, and feedback.",
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        content = render_markdown(draft, "raw/inbox/notes/agent.md", "abc123")

        self.assertIn("# Agent Loop", content)
        self.assertIn("created:", content)
        self.assertIn("updated:", content)
        self.assertIn("content_hash: abc123", content)
        self.assertNotIn("source: raw/inbox/notes/agent.md", content)
        self.assertIn("## Claims\n\n- C1: [[Agent Loop]] repeats observe, decide, act, and feedback.", content)
        self.assertIn("## Evidence", content)
        self.assertIn("| C1 | raw/inbox/notes/agent.md | section:Agent Loop | source states the loop steps | high |", content)

    def test_render_markdown_rejects_missing_evidence_for_knowledge_page(self) -> None:
        draft = WikiDraft(
            title="Agent Loop",
            page_dir="pages",
            question="Agent loop",
            synthesis="Agent loop repeats observe, decide, act, and feedback.",
            summary="Agent loop is a control pattern.",
            claims=["C1: Agent loop repeats observe, decide, act, and feedback."],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        with self.assertRaisesRegex(Exception, "require explicit evidence"):
            render_markdown(draft, "raw/inbox/notes/agent.md", "abc123")

    def test_render_source_digest_includes_attachments(self) -> None:
        draft = WikiDraft(
            title="Parsed Paper Source",
            page_dir="sources",
            role="source_digest",
            question="Parsed Paper",
            synthesis="Audit record.",
            summary="Audit record.",
            evidence=["U1 | raw/inbox/documents/paper.pdf | unit:0 | parsed source | high"],
            attachments=[
                {
                    "attachment_type": "image",
                    "name": "figure-1.png",
                    "topic": "Agent architecture",
                    "description": "Architecture figure.",
                    "relative_path": "images/figure-1.png",
                    "source_range": "page_idx:0",
                    "content_hash": "abcdef1234567890",
                }
            ],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
            source_digest_ids=["sd_test"],
        )

        content = render_markdown(draft, "raw/inbox/documents/paper.pdf", "abc123")

        self.assertIn("## Attachments", content)
        self.assertLess(content.index("## Contribution Map"), content.index("## Attachments"))
        self.assertIn("| Attachment | Type | Topic | Description | Source Range | Status |", content)
        self.assertIn("| A1 | image | Agent architecture | Architecture figure. | page_idx:0 | candidate |", content)
        self.assertNotIn("![", content)
        self.assertNotIn("abcdef123456", content)
        self.assertNotIn("images/figure-1.png", content)

    def test_render_knowledge_page_attachments_as_readable_triples(self) -> None:
        draft = WikiDraft(
            title="AC1",
            page_dir="pages",
            question="AC1",
            summary="AC1 summary.",
            claims=["C1: [[AC1]] has a LiDAR FOV diagram."],
            entities=["[[AC1]]"],
            relations=["[[AC1]] | has | [[LiDAR FOV Diagram]] | C1"],
            evidence=["C1 | sd_ac1 | unit:0 | AC1 document includes the FOV diagram. | high"],
            synthesis="AC1 synthesis.",
            attachments=[
                {
                    "attachment_type": "image",
                    "name": "0904cb558f84ae5957d99f7b85b9bc6897c00c3c4950e176e353ba393c257bf3.jpg",
                    "description": "",
                    "relative_path": "images/0904cb558f84ae5957d99f7b85b9bc6897c00c3c4950e176e353ba393c257bf3.jpg",
                },
                {
                    "attachment_type": "image",
                    "topic": "AC1 激光雷达 FOV 分布图",
                    "description": "说明激光雷达的水平和垂直 FOV 覆盖范围。",
                    "relative_path": "images/fov.jpg",
                },
            ],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        content = render_markdown(draft, "raw/inbox/documents/AC1.md", "abc123")

        self.assertIn("## Attachments", content)
        self.assertNotIn("| Topic | Description | Path |", content)
        self.assertIn("| Topic | Description |", content)
        self.assertIn("| AC1 激光雷达 FOV 分布图 | 说明激光雷达的水平和垂直 FOV 覆盖范围。 |", content)
        self.assertNotIn("0904cb558f84ae5957d99f7b85b9bc6897c00c3c4950e176e353ba393c257bf3.jpg", content)
        self.assertNotIn("images/fov.jpg", content)
        self.assertNotIn("![", content)

    def test_render_markdown_rejects_outer_body_headings(self) -> None:
        draft = WikiDraft(
            title="LLM Wiki",
            page_dir="pages",
            question="Source focus",
            synthesis="# Overview\n\n## Details",
            summary="## Summary Heading",
            claims=["C1: Invalid headings should be rejected."],
            evidence=["C1 | raw/inbox/notes/wiki.md | section:Wiki | source support | high"],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        with self.assertRaisesRegex(ValueError, "must not contain H1/H2"):
            render_markdown(draft, "raw/inbox/notes/wiki.md", "abc123")

    def test_apply_patched_markdown_merges_lists(self) -> None:
        draft = WikiDraft(
            title="Agent Loop",
            page_dir="pages",
            question="Agent loop",
            synthesis="Updated answer.",
            summary="Updated summary.",
            claims=["C1: Updated answer."],
            evidence=["C1 | raw/inbox/notes/agent.md | section:Agent | source support | high"],
            confidence=0.9,
            model_provider="test",
            model_name="unit",
            patches=[
                WikiPatchInput(
                    operation="merge_list",
                    section="Entities",
                    items=["[[ReAct]]"],
                )
            ],
        )
        existing = (
            "---\nupdated: old\ncontent_hash: old\nconfidence: 0.1\nmodel_provider: old\nmodel_name: old\n---\n"
            "# Agent Loop\n\n## Entities\n\n- [[Agent Loop]]"
        )

        content = apply_patched_markdown(existing, draft, "raw/inbox/notes/agent.md", "newhash")

        self.assertIn("- [[Agent Loop]]\n- [[ReAct]]", content)


if __name__ == "__main__":
    unittest.main()
