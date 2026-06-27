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

    def test_operation_pipeline_adds_missing_required_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "RAG.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# RAG\n\n## Summary\n\nRAG notes.\n",
                encoding="utf-8",
            )

            response = WikiOperationPipeline().apply(
                WikiOperationApplyRequest(
                    vault_path=str(vault),
                    operations=[
                        WikiOperationInput(
                            operation_id="op-section",
                            action="add_missing_section",
                            target_page="RAG.md",
                            reason="Add required Evidence section.",
                            risk_level="safe",
                            confidence=0.95,
                            expected_effect="Page has the required Evidence section.",
                            section="Evidence",
                        )
                    ],
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.stats["applied_count"], 1)
        self.assertIn("## Evidence\n\n- 暂无证据", content)
        self.assertEqual(response.results[0].details["section"], "Evidence")

    def test_operation_pipeline_removes_adjacent_duplicate_headings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.write_text(
                "# Agent\n\n## Summary\n\n### Control\n\n### Control\n\nLoop details.\n",
                encoding="utf-8",
            )

            response = WikiOperationPipeline().apply(
                WikiOperationApplyRequest(
                    vault_path=str(vault),
                    operations=[
                        WikiOperationInput(
                            operation_id="op-heading",
                            action="remove_adjacent_duplicate_headings",
                            target_page="Agent.md",
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

    def test_redact_sensitive_text_redacts_generated_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "sources").mkdir(parents=True)
            page = vault / "wiki" / "sources" / "Agent.md"
            page.write_text(
                "# Agent\n\n## Summary\n\n"
                "Key sk-abcdefghijklmnop1234567890, app cli_aa9f1cd454399bc8, path /Users/alice/private.\n",
                encoding="utf-8",
            )

            response = WikiOperationPipeline().apply(
                WikiOperationApplyRequest(
                    vault_path=str(vault),
                    operations=[
                        WikiOperationInput(
                            operation_id="op-redact",
                            action="redact_sensitive_text",
                            target_page="sources/Agent.md",
                            reason="Remove sensitive generated-page content.",
                            risk_level="safe",
                            confidence=0.95,
                            expected_effect="Sensitive values are replaced by redaction placeholders.",
                        )
                    ],
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.results[0].status, "applied")
        self.assertIn("[REDACTED_API_KEY]", content)
        self.assertIn("[REDACTED_PLATFORM_ID]", content)
        self.assertIn("/Users/[REDACTED_USER]/private", content)
        self.assertNotIn("sk-abcdefghijklmnop", content)
        self.assertNotIn("cli_aa9f", content)


if __name__ == "__main__":
    unittest.main()
