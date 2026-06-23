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
            page_dir="concepts",
            page_type="concept",
            question="Agent loop",
            answer="Agent loop repeats observe, decide, act, and feedback.",
            summary="Agent loop is a control pattern.",
            claims=["C1: [[Agent Loop]] repeats observe, decide, act, and feedback."],
            entities=["[[Agent Loop]]"],
            relations=["[[Agent Loop]] | repeats | [[Control Cycle]] | C1"],
            evidence=["C1 | raw/notes/agent.md | section:Agent Loop | source states the loop steps | high"],
            synthesis="Agent loop repeats observe, decide, act, and feedback.",
            key_points=["Observe, decide, act."],
            tags=["agent", "loop"],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        content = render_markdown(draft, ["[[concepts/ReAct|ReAct]]"], "raw/notes/agent.md", "abc123")

        self.assertIn("# Agent Loop", content)
        self.assertIn("created:", content)
        self.assertIn("updated:", content)
        self.assertIn("content_hash: abc123", content)
        self.assertNotIn("source: raw/notes/agent.md", content)
        self.assertIn("## Claims\n\n- C1: [[Agent Loop]] repeats observe, decide, act, and feedback.", content)
        self.assertIn("## Evidence", content)
        self.assertIn("| C1 | raw/notes/agent.md | section:Agent Loop | source states the loop steps | high |", content)
        self.assertNotIn("## Related Pages", content)

    def test_render_markdown_rejects_missing_evidence_for_knowledge_page(self) -> None:
        draft = WikiDraft(
            title="Agent Loop",
            page_dir="concepts",
            page_type="concept",
            question="Agent loop",
            answer="Agent loop repeats observe, decide, act, and feedback.",
            summary="Agent loop is a control pattern.",
            claims=["C1: Agent loop repeats observe, decide, act, and feedback."],
            key_points=["Observe, decide, act."],
            tags=["agent", "loop"],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        with self.assertRaisesRegex(Exception, "require explicit evidence"):
            render_markdown(draft, [], "raw/notes/agent.md", "abc123")

    def test_render_markdown_rejects_outer_body_headings(self) -> None:
        draft = WikiDraft(
            title="LLM Wiki",
            page_dir="concepts",
            page_type="concept",
            question="# Source Focus",
            answer="# Overview\n\n## Details",
            summary="## Summary Heading",
            claims=["C1: Invalid headings should be rejected."],
            evidence=["C1 | raw/notes/wiki.md | section:Wiki | source support | high"],
            key_points=["Point"],
            tags=["wiki"],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        with self.assertRaisesRegex(ValueError, "must not contain H1/H2"):
            render_markdown(draft, [], "raw/notes/wiki.md", "abc123")

    def test_apply_patched_markdown_merges_lists(self) -> None:
        draft = WikiDraft(
            title="Agent Loop",
            page_dir="concepts",
            page_type="concept",
            question="Agent loop",
            answer="Updated answer.",
            summary="Updated summary.",
            claims=["C1: Updated answer."],
            evidence=["C1 | raw/notes/agent.md | section:Agent | source support | high"],
            key_points=[],
            tags=[],
            confidence=0.9,
            model_provider="test",
            model_name="unit",
            patches=[
                WikiPatchInput(
                    operation="merge_list",
                    section="Key Points",
                    items=["New point"],
                )
            ],
        )
        existing = (
            "---\nupdated: old\ncontent_hash: old\nconfidence: 0.1\nmodel_provider: old\nmodel_name: old\n---\n"
            "# Agent Loop\n\n## Key Points\n\n- Existing point\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/old.md\n"
        )

        content = apply_patched_markdown(existing, draft, ["[[concepts/ReAct|ReAct]]"], "raw/notes/agent.md", "newhash")

        self.assertIn("- Existing point\n- New point", content)
        self.assertNotIn("- [[concepts/ReAct|ReAct]]", content)
        self.assertIn("- raw/old.md", content)


if __name__ == "__main__":
    unittest.main()
