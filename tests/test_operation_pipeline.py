from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import get_args

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.wiki_operation import WikiOperationApplyRequest, WikiOperationInput
from knoarbor.core.schemas.wiki_operation import WikiOperationAction
from knoarbor.core.errors import PolicyRejection
from knoarbor.pipelines.lint_execution import _WIKI_OPERATION_ACTIONS
from knoarbor.pipelines import WikiOperationPipeline


class WikiOperationPipelineTests(unittest.TestCase):
    def test_lint_execution_action_map_matches_public_operation_schema(self) -> None:
        self.assertEqual(set(get_args(WikiOperationAction)), _WIKI_OPERATION_ACTIONS)

    def test_operation_pipeline_updates_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            page = vault / "concepts" / "Agent.md"
            page.write_text(
                "---\ntype: concept\nstatus: draft\n---\n# Agent\n\n## Summary\n\nAgent notes.\n",
                encoding="utf-8",
            )

            response = WikiOperationPipeline().apply(
                WikiOperationApplyRequest(
                    obsidian_vault_path=str(vault),
                    operations=[
                        WikiOperationInput(
                            operation_id="op-1",
                            action="update_frontmatter",
                            target_page="concepts/Agent.md",
                            reason="Mark reviewed after deterministic test.",
                            risk_level="safe",
                            confidence=0.95,
                            expected_effect="Status becomes reviewed.",
                            frontmatter={"status": "reviewed"},
                        )
                    ],
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.stats["applied_count"], 1)
        self.assertIn("status: reviewed", content)
        self.assertEqual(response.results[0].status, "applied")

    def test_operation_pipeline_adds_missing_required_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            page = vault / "concepts" / "RAG.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/rag.md\ncontent_hash: a\ntags: rag, evaluation\n---\n"
                "# RAG\n\n## Summary\n\nRAG notes.\n\n## Source\n\n- raw/notes/rag.md\n",
                encoding="utf-8",
            )

            response = WikiOperationPipeline().apply(
                WikiOperationApplyRequest(
                    obsidian_vault_path=str(vault),
                    operations=[
                        WikiOperationInput(
                            operation_id="op-section",
                            action="add_missing_section",
                            target_page="concepts/RAG.md",
                            reason="Add required Tags section.",
                            risk_level="safe",
                            confidence=0.95,
                            expected_effect="Page has the required Tags section.",
                            section="Tags",
                        )
                    ],
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.stats["applied_count"], 1)
        self.assertIn("## Tags\n\n- rag\n- evaluation", content)
        self.assertEqual(response.results[0].details["section"], "Tags")

    def test_operation_pipeline_removes_adjacent_duplicate_headings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            page = vault / "concepts" / "Agent.md"
            page.write_text(
                "# Agent\n\n## Summary\n\n### Control\n\n### Control\n\nLoop details.\n",
                encoding="utf-8",
            )

            response = WikiOperationPipeline().apply(
                WikiOperationApplyRequest(
                    obsidian_vault_path=str(vault),
                    operations=[
                        WikiOperationInput(
                            operation_id="op-heading",
                            action="remove_adjacent_duplicate_headings",
                            target_page="concepts/Agent.md",
                            reason="Remove adjacent duplicate heading.",
                            risk_level="safe",
                            confidence=0.98,
                            expected_effect="Only one Control heading remains.",
                        )
                    ],
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.stats["applied_count"], 1)
        self.assertEqual(content.count("### Control"), 1)
        self.assertEqual(response.results[0].details["removed_count"], 1)

    def test_operation_pipeline_adds_missing_query_question_from_source_focus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "queries").mkdir()
            page = vault / "queries" / "Plan.md"
            page.write_text(
                "---\ntype: query\nstatus: draft\nsource: raw/chats/session.json\ncontent_hash: a\n---\n"
                "# Study Plan\n\n## Summary\n\nPlan notes.\n\n## Source Focus\n\nHow should I plan graduate study?\n\n## Answer\n\nStudy steadily.\n",
                encoding="utf-8",
            )

            WikiOperationPipeline().apply(
                WikiOperationApplyRequest(
                    obsidian_vault_path=str(vault),
                    operations=[
                        WikiOperationInput(
                            operation_id="op-question",
                            action="add_missing_section",
                            target_page="queries/Plan.md",
                            reason="Add required Question section.",
                            risk_level="safe",
                            confidence=0.95,
                            expected_effect="Page has the required Question section.",
                            section="Question",
                        )
                    ],
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertIn("## Question\n\nHow should I plan graduate study?", content)

    def test_update_source_field_rejects_serialized_list_source_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "sources").mkdir()
            page = vault / "sources" / "Agent.md"
            page.write_text(
                "---\ntype: source\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PolicyRejection, "single source_file string"):
                WikiOperationPipeline().apply(
                    WikiOperationApplyRequest(
                        obsidian_vault_path=str(vault),
                        operations=[
                            WikiOperationInput(
                                operation_id="op-source",
                                action="update_source_field",
                                target_page="sources/Agent.md",
                                reason="Reject malformed provenance.",
                                risk_level="safe",
                                confidence=0.95,
                                expected_effect="Malformed source is not written.",
                                source_file="['raw/notes/agent.md', 'raw/notes/other.md']",
                            )
                        ],
                    )
                )

            self.assertNotIn("['raw/notes", page.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
