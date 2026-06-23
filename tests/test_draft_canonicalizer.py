from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.wiki_write import WikiDraftInput
from knoarbor.pipelines.draft_canonicalizer import DraftCanonicalizer


class DraftCanonicalizerTests(unittest.TestCase):
    def test_canonicalizes_source_digest_and_body_shape(self) -> None:
        draft = WikiDraftInput(
            title="LLM-Wiki.md",
            page_dir="sources",
            question="# Source Context",
            answer="# Overview\n\n## Details",
            summary="## Summary",
            key_points=["Point"],
            tags=["Knowledge Management"],
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        result = DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/notes/LLM-Wiki.md", write_action="create")

        self.assertEqual(result.draft.title, "LLM-Wiki Source")
        self.assertEqual(result.draft.page_kind, "source_digest")
        self.assertEqual(result.draft.subject_kind, "source_digest")
        self.assertEqual(result.draft.question, "### Source Context")
        self.assertIn("### Overview", result.draft.answer)
        self.assertEqual(result.draft.tags, [])
        self.assertIn("normalized_title", result.changes)
        self.assertIn("normalized_body_headings", result.changes)

    def test_legacy_fields_do_not_backfill_claims_or_facets(self) -> None:
        draft = WikiDraftInput(
            title="Agent Loop",
            page_dir="concepts",
            question="Agent Loop",
            answer="Agent loop repeats reasoning and tool use.",
            summary="Agent loop is a control pattern.",
            key_points=["Legacy point should not become a claim."],
            tags=["Legacy Tag"],
            facets=["agent-control"],
        )

        result = DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/notes/agent.md", write_action="create")

        self.assertEqual(result.draft.claims, [])
        self.assertEqual(result.draft.key_points, [])
        self.assertEqual(result.draft.tags, [])
        self.assertIn("agent_control", result.draft.facets)
        self.assertNotIn("legacy_tag", result.draft.facets)

    def test_preserves_atom_trace_fields(self) -> None:
        draft = WikiDraftInput(
            title="Agent Loop",
            page_dir="concepts",
            question="Agent Loop",
            answer="Agent loop repeats reasoning and tool use.",
            summary="Agent loop is a control pattern.",
            source_digest_ids=[" sd_agent ", "sd_agent"],
            atom_ids=["fact_agent_loop", " fact_agent_loop "],
        )

        result = DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/notes/agent.md", write_action="create")

        self.assertEqual(result.draft.source_digest_ids, ["sd_agent"])
        self.assertEqual(result.draft.atom_ids, ["fact_agent_loop"])

    def test_rejects_placeholder_source_file(self) -> None:
        draft = WikiDraftInput(
            title="LLM Wiki",
            page_dir="concepts",
            question="LLM Wiki",
            answer="Body",
            summary="Summary",
        )

        with self.assertRaisesRegex(ValueError, "placeholder"):
            DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/source/path", write_action="create")

    def test_rejects_unclosed_fenced_code_block_in_patch(self) -> None:
        draft = WikiDraftInput(
            title="Deploy",
            page_dir="workflows",
            question="Rewrite workflow steps",
            answer="Body",
            summary="Summary",
            patches=[
                {
                    "operation": "replace_section",
                    "section": "Steps",
                    "content": "1. Run:\n```bash\necho deploy",
                }
            ],
        )

        with self.assertRaisesRegex(ValueError, "unclosed fenced code block"):
            DraftCanonicalizer().canonicalize_draft(draft, source_file=None, write_action="update")

    def test_canonicalizes_written_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Known.md").write_text("# Known\n", encoding="utf-8")

            result = DraftCanonicalizer().canonicalize_written_content(
                vault,
                "Keep [[concepts/Known|Known]] and remove [[Missing Page]].",
            )

        self.assertIn("[[concepts/Known|Known]]", result.content)
        self.assertIn("remove Missing Page", result.content)
        self.assertEqual(result.removed_wikilinks, ["Missing Page"])


if __name__ == "__main__":
    unittest.main()
