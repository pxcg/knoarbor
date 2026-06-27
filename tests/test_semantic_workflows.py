from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan
from knoarbor.semantic.ingest_workflow import IngestSemanticWorkflow
from knoarbor.semantic.lint_workflow import LintSemanticWorkflow
from knoarbor.semantic.runner import SemanticRunResult


class FakeDraftCompileRunner:
    def __init__(self) -> None:
        self.history: list[SemanticRunResult] = []

    def run(self, contract_name: str, payload: dict[str, Any], **kwargs: Any) -> SemanticRunResult:
        if contract_name not in {"wiki_draft_compile", "lint_draft_compile"}:
            raise AssertionError(f"Unexpected contract: {contract_name}")
        batch = WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action="create",
                    title="Agent Loop",
                    page_dir="pages",
                    question="Agent Loop",
                    synthesis="Agent loop alternates reasoning, action, and observation.",
                    summary="Agent loop is a control pattern.",
                    model_provider="prompt-example",
                    model_name="prompt-example-model",
                )
            ],
            batch_summary="One draft.",
        )
        result = SemanticRunResult(
            contract_name=contract_name,
            schema_version="wiki_draft_batch.v1",
            provider="deepseek",
            model="deepseek-v4-flash",
            output=batch,
        )
        self.history.append(result)
        return result


class SemanticWorkflowTests(unittest.TestCase):
    def test_ingest_compile_drafts_uses_runtime_model_metadata(self) -> None:
        workflow = IngestSemanticWorkflow(FakeDraftCompileRunner())  # type: ignore[arg-type]

        batch = workflow.compile_drafts(_knowledge_extract(), _page_plan())

        self.assertEqual(batch.drafts[0].model_provider, "deepseek")
        self.assertEqual(batch.drafts[0].model_name, "deepseek-v4-flash")

    def test_lint_compile_drafts_uses_runtime_model_metadata(self) -> None:
        workflow = LintSemanticWorkflow(FakeDraftCompileRunner())  # type: ignore[arg-type]

        batch = workflow.compile_drafts({"approved_operations": []})

        self.assertEqual(batch.drafts[0].model_provider, "deepseek")
        self.assertEqual(batch.drafts[0].model_name, "deepseek-v4-flash")


def _knowledge_extract() -> KnowledgeExtract:
    return KnowledgeExtract.model_validate(
        {
            "schema_version": "knowledge_extract.v1",
            "source": {
                "source_type": "markdown",
                "source_app": "markdown",
                "source_id": "markdown:agent-loop",
                "title": "Agent Loop",
            },
            "compile_context": {
                "primary_content": "Agent loop alternates reasoning, action, and observation.",
            },
            "confidence": 0.9,
        }
    )


def _page_plan() -> WikiPagePlan:
    return WikiPagePlan(
        operations=[
            WikiPageOperation(
                action="create",
                page_dir="pages",
                title="Agent Loop",
                knowledge_object="Agent Loop",
                selected_claim_ids=["claim_agent_loop"],
                source_digest_ids=["sd_agent"],
                decision_reason="Stable concept.",
            )
        ],
        overall_summary="Create concept page.",
    )


if __name__ == "__main__":
    unittest.main()
