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
            key_points=["Observe, decide, act."],
            tags=["agent", "loop"],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        content = render_markdown(draft, ["[[concepts/ReAct|ReAct]]"], "raw/notes/agent.md", "abc123")

        self.assertIn("# Agent Loop", content)
        self.assertIn("source: raw/notes/agent.md", content)
        self.assertIn("## Related Pages\n\n- [[concepts/ReAct|ReAct]]", content)

    def test_render_markdown_rejects_outer_body_headings(self) -> None:
        draft = WikiDraft(
            title="LLM Wiki",
            page_dir="concepts",
            page_type="concept",
            question="# Source Focus",
            answer="# Overview\n\n## Details",
            summary="## Summary Heading",
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
        self.assertIn("- [[concepts/ReAct|ReAct]]", content)
        self.assertIn("- raw/notes/agent.md", content)


if __name__ == "__main__":
    unittest.main()
