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
            synthesis="# Overview\n\n## Details",
            summary="## Summary",
            confidence=0.8,
            model_provider="test",
            model_name="unit",
        )

        result = DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/inbox/notes/LLM-Wiki.md", write_action="create")

        self.assertEqual(result.draft.title, "LLM-Wiki Source")
        self.assertEqual(result.draft.role, "source_digest")
        self.assertEqual(result.draft.question, "### Source Context")
        self.assertIn("### Overview", result.draft.synthesis)
        self.assertIn("normalized_title", result.changes)
        self.assertIn("normalized_body_headings", result.changes)

    def test_identity_fields_do_not_backfill_claims(self) -> None:
        draft = WikiDraftInput(
            title="Agent Loop",
            page_dir="pages",
            question="Agent Loop",
            synthesis="Agent loop repeats reasoning and tool use.",
            summary="Agent loop is a control pattern.",
        )

        result = DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/inbox/notes/agent.md", write_action="create")

        self.assertEqual(result.draft.claims, [])
        self.assertEqual(result.draft.role, "knowledge_page")

    def test_preserves_atom_trace_fields(self) -> None:
        draft = WikiDraftInput(
            title="Agent Loop",
            page_dir="pages",
            question="Agent Loop",
            synthesis="Agent loop repeats reasoning and tool use.",
            summary="Agent loop is a control pattern.",
            source_digest_ids=[" sd_agent ", "sd_agent"],
            atom_ids=["fact_agent_loop", " fact_agent_loop "],
        )

        result = DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/inbox/notes/agent.md", write_action="create")

        self.assertEqual(result.draft.source_digest_ids, ["sd_agent"])
        self.assertEqual(result.draft.atom_ids, ["fact_agent_loop"])

    def test_preserves_attachments(self) -> None:
        draft = WikiDraftInput(
            title="AC1",
            page_dir="pages",
            question="AC1",
            summary="AC1 includes a lidar FOV figure.",
            claims=["C1: [[AC1]] includes a lidar FOV figure."],
            entities=["[[AC1]]"],
            relations=["[[AC1]] | includes | [[Lidar FOV Figure]] | C1"],
            evidence=["C1 | raw/inbox/documents/AC1.pdf | page:3 | figure caption | high"],
            attachments=[
                {
                    "name": "AC1 激光雷达FOV分布图",
                    "kind": "image",
                    "relative_path": "images/ac1-fov.png",
                    "description": "AC1 激光雷达 FOV 分布图。",
                    "topic": "激光雷达 FOV",
                }
            ],
            synthesis="AC1 includes a lidar FOV figure.",
        )

        result = DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/inbox/documents/AC1.pdf", write_action="create")

        self.assertEqual(result.draft.attachments, draft.attachments)

    def test_rejects_placeholder_source_file(self) -> None:
        draft = WikiDraftInput(
            title="LLM Wiki",
            page_dir="pages",
            question="LLM Wiki",
            synthesis="Body",
            summary="Summary",
        )

        with self.assertRaisesRegex(ValueError, "placeholder"):
            DraftCanonicalizer().canonicalize_draft(draft, source_file="raw/source/path", write_action="create")

    def test_rejects_unclosed_fenced_code_block_in_patch(self) -> None:
        draft = WikiDraftInput(
            title="Deploy",
            page_dir="pages",
            question="Rewrite workflow steps",
            synthesis="Body",
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
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Known.md").write_text("# Known\n", encoding="utf-8")

            result = DraftCanonicalizer().canonicalize_written_content(
                vault,
                "Keep [[Known|Known]] and remove [[Missing Page]].",
            )

        self.assertIn("[[Known|Known]]", result.content)
        self.assertIn("remove Missing Page", result.content)
        self.assertEqual(result.removed_wikilinks, ["Missing Page"])


if __name__ == "__main__":
    unittest.main()
