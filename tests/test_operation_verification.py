from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteResponse
from knoarbor.maintenance.operation_verification import verify_lint_post_fixes


class OperationVerificationTest(unittest.TestCase):
    def test_verifies_adjacent_duplicate_headings_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "# Agent\n\n## Summary\n\n### Control\n\nLoop details.\n",
                encoding="utf-8",
            )

            verifications = verify_lint_post_fixes(
                vault,
                applied_operations=[
                    {
                        "operation_id": "op-1",
                        "action": "remove_adjacent_duplicate_headings",
                        "target_page": "Agent.md",
                        "output_page": "Agent.md",
                    }
                ],
            )

        self.assertEqual(verifications[0].status, "verified")

    def test_fails_when_adjacent_duplicate_headings_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "# Agent\n\n## Summary\n\n### Control\n\n### Control\n\nLoop details.\n",
                encoding="utf-8",
            )

            verifications = verify_lint_post_fixes(
                vault,
                applied_operations=[
                    {
                        "operation_id": "op-1",
                        "action": "remove_adjacent_duplicate_headings",
                        "target_page": "Agent.md",
                        "output_page": "Agent.md",
                    }
                ],
            )

        self.assertEqual(verifications[0].status, "failed")
        self.assertIn("adjacent duplicate headings", verifications[0].reason)

    def test_verifies_rename_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text("# Agent Loop\n", encoding="utf-8")

            verifications = verify_lint_post_fixes(
                vault,
                applied_operations=[
                    {
                        "operation_id": "op-1",
                        "action": "rename_page",
                        "target_page": "Agent.md",
                        "output_page": "Agent-Loop.md",
                        "details": {"old_path": "Agent.md", "new_path": "Agent-Loop.md"},
                    }
                ],
            )

        self.assertEqual(verifications[0].status, "verified")

    def test_verifies_archived_delete_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "maintenance" / "archives" / "deleted_pages").mkdir(parents=True)
            archive = "maintenance/archives/deleted_pages/20260523_Agent.md"
            (vault / archive).write_text("# Agent\n", encoding="utf-8")

            verifications = verify_lint_post_fixes(
                vault,
                applied_operations=[
                    {
                        "operation_id": "op-1",
                        "action": "delete_page",
                        "target_page": "Agent.md",
                        "output_page": archive,
                        "details": {"archived_instead_of_removed": True},
                    }
                ],
            )

        self.assertEqual(verifications[0].status, "verified")

    def test_verifies_merge_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "maintenance" / "archives" / "merged_pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "# Agent\n\n## Merged Notes\n\n### Agent Duplicate\n\nSource page: [[Agent-Duplicate|Agent Duplicate]]\n",
                encoding="utf-8",
            )
            (vault / "maintenance" / "archives" / "merged_pages" / "20260523_Agent-Duplicate.md").write_text("# Agent Duplicate\n", encoding="utf-8")

            verifications = verify_lint_post_fixes(
                vault,
                applied_operations=[
                    {
                        "operation_id": "op-1",
                        "action": "merge_pages",
                        "target_page": "Agent.md",
                        "output_page": "Agent.md",
                        "details": {"merged_sources": ["Agent-Duplicate.md"], "archived_sources": True},
                    }
                ],
            )

        self.assertEqual(verifications[0].status, "verified")

    def test_verifies_improve_summary_draft_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.parent.mkdir(parents=True)
            content = (
                "---\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop coordinates model reasoning and tool execution.\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/Agent.md | unit:0 | Agent notes. | medium |\n"
            )
            page.write_text(content, encoding="utf-8")

            verifications = verify_lint_post_fixes(
                vault,
                applied_operations=[],
                draft_batch=WikiDraftBatch.model_validate(
                    {
                        "drafts": [
                            {
                                "operation_index": 0,
                                "write_action": "update",
                                "target_page": "Agent.md",
                                "title": "Agent",
                                "page_dir": "pages",
                                "question": "What is Agent?",
                                "summary": "Agent loop coordinates model reasoning and tool execution.",
                                "synthesis": "Agent loop coordinates model reasoning and tool execution.",
                                "patches": [
                                    {
                                        "operation": "replace_section",
                                        "section": "Summary",
                                        "content": "Agent loop coordinates model reasoning and tool execution.",
                                    }
                                ],
                            }
                        ],
                        "batch_summary": "summary patch",
                    }
                ),
                draft_write_response=WikiDraftBatchWriteResponse.model_validate(
                    {
                        "results": [
                            {
                                "wiki_file_path": str(page),
                                "wiki_md_content": content,
                                "stats": {
                                    "write_action": "update",
                                    "operation_index": 0,
                                    "write_details": {"patched_sections": ["Summary"]},
                                },
                            }
                        ],
                        "stats": {},
                    }
                ),
                candidates=MaintenanceCandidates.model_validate(
                    {
                        "candidates": [
                            {
                                "candidate_id": "quality:Agent.md:poor_summary:0",
                                "source": "quality",
                                "target_page": "Agent.md",
                                "issue_type": "poor_summary",
                                "severity": "low",
                                "confidence": 0.9,
                                "risk_hint": "low",
                                "executor_hint": "draft_write",
                                "recommended_action": {"action": "improve_summary", "params": {}},
                                "expected_effect": "better summary",
                                "review_notes": "summary only",
                            }
                        ],
                        "summary": "candidate",
                    }
                ),
            )

        self.assertEqual(verifications[0].status, "verified")
        self.assertEqual(verifications[0].action, "improve_summary")

    def test_fails_add_missing_section_when_section_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.parent.mkdir(parents=True)
            content = (
                "---\n---\n"
                "# Agent\n\n## Summary\n\nAgent summary.\n"
            )
            page.write_text(content, encoding="utf-8")

            verifications = verify_lint_post_fixes(
                vault,
                applied_operations=[],
                draft_batch=WikiDraftBatch.model_validate(
                    {
                        "drafts": [
                            {
                                "operation_index": 0,
                                "write_action": "update",
                                "target_page": "Agent.md",
                                "title": "Agent",
                                "page_dir": "pages",
                                "question": "What is Agent?",
                                "summary": "Agent summary.",
                                "synthesis": "Agent summary.",
                                "patches": [
                                    {
                                        "operation": "append_section",
                                        "section": "Claims",
                                        "items": ["Agent coordinates model and tools."],
                                    }
                                ],
                            }
                        ],
                        "batch_summary": "add claims",
                    }
                ),
                draft_write_response=WikiDraftBatchWriteResponse.model_validate(
                    {
                        "results": [
                            {
                                "wiki_file_path": str(page),
                                "wiki_md_content": content,
                                "stats": {
                                    "write_action": "update",
                                    "operation_index": 0,
                                    "write_details": {"patched_sections": ["Claims"]},
                                },
                            }
                        ],
                        "stats": {},
                    }
                ),
                candidates=MaintenanceCandidates.model_validate(
                    {
                        "candidates": [
                            {
                                "candidate_id": "quality:Agent.md:missing_claims:0",
                                "source": "quality",
                                "target_page": "Agent.md",
                                "issue_type": "missing_claims",
                                "severity": "low",
                                "confidence": 0.9,
                                "risk_hint": "low",
                                "executor_hint": "draft_write",
                                "recommended_action": {"action": "add_missing_section", "params": {"section": "Claims"}},
                                "expected_effect": "claims section exists",
                                "review_notes": "section only",
                            }
                        ],
                        "summary": "candidate",
                    }
                ),
            )

        self.assertEqual(verifications[0].status, "failed")
        self.assertIn("missing or empty", verifications[0].reason)


if __name__ == "__main__":
    unittest.main()
