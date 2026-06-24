from __future__ import annotations

import unittest

from knoarbor.core.schemas.ingest_review import (
    IngestDraftReview,
    IngestDraftReviewDecision,
    IngestReviewChecks,
    IngestReviewDimensionScores,
)
from knoarbor.core.schemas.knowledge_extract import CompileContext, ContentUnit, KnowledgeExtract, KnowledgeSource
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan
from knoarbor.pipelines.ingest_context import IngestCandidatePageContext
from knoarbor.pipelines.ingest_write_gate import IngestWriteGate
from knoarbor.semantic.ingest_workflow import IngestSemanticWorkflowResult


class IngestWriteGateTests(unittest.TestCase):
    def test_source_page_allows_source_unit_evidence(self) -> None:
        result = _semantic_result_with_source_draft()
        gate = IngestWriteGate().validate(
            result,
            [0],
            candidate_page_context=IngestCandidatePageContext(pages=[], stats={}),
        )

        self.assertTrue(gate.passed, [issue.model_dump() for issue in gate.issues])


def _semantic_result_with_source_draft() -> IngestSemanticWorkflowResult:
    return IngestSemanticWorkflowResult(
        knowledge_extract=KnowledgeExtract(
            source=KnowledgeSource(
                source_type="markdown",
                source_app="markdown",
                source_id="markdown:memory",
                source_path="raw/notes/Memory.md",
                title="Memory",
            ),
            content_units=[ContentUnit(index=0, unit_type="note", role="note", content="Memory strategies.")],
            compile_context=CompileContext(primary_content="Memory strategies."),
        ),
        source_digest=SourceDigest(
            digest_id="sd_memory",
            source=KnowledgeSource(
                source_type="markdown",
                source_app="markdown",
                source_id="markdown:memory",
                source_path="raw/notes/Memory.md",
                title="Memory",
            ),
            raw_source="raw/notes/Memory.md",
            content_hash="abc",
            source_focus="Memory",
            summary="Memory strategies.",
        ),
        knowledge_atom_batch=KnowledgeAtomBatch(source_digest_id="sd_memory"),
        knowledge_atom_quality=None,
        wiki_page_plan=WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action="create",
                    page_dir="sources",
                    title="Memory Source",
                    knowledge_object="Memory Source",
                    source_digest_ids=["sd_memory"],
                    decision_reason="Create source audit page.",
                )
            ],
            overall_summary="Create source page.",
        ),
        wiki_draft_batch=WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action="create",
                    source_file="raw/notes/Memory.md",
                    title="Memory Source",
                    page_dir="sources",
                    question="Memory Source",
                    answer="Source audit page.",
                    summary="Source audit page.",
                    claims=[],
                    entities=[],
                    relations=[],
                    evidence=["U1 | raw/notes/Memory.md | unit:0 | source unit basis | high"],
                    synthesis="Source audit page.",
                    source_digest_ids=["sd_memory"],
                    atom_ids=[],
                )
            ],
            batch_summary="One source draft.",
        ),
        ingest_draft_review=IngestDraftReview(
            decisions=[_make_review(0)],
            batch_decision="approve",
            summary="Approved.",
        ),
    )


def _make_review(operation_index: int) -> IngestDraftReviewDecision:
    return IngestDraftReviewDecision(
        operation_index=operation_index,
        decision="approve",
        quality_score=0.9,
        risk_level="low",
        write_safety="safe_create",
        reason="Safe source audit page.",
        dimension_scores=IngestReviewDimensionScores(
            source_trace=0.9,
            atom_coverage=0.9,
            source_support=0.9,
            page_boundary=0.9,
            identity_fit=0.9,
            duplication_risk=0.9,
            relation_quality=0.9,
            synthesis_quality=0.9,
            maintainability=0.9,
            update_safety=0.9,
        ),
        checks=IngestReviewChecks(
            operation_aligned=True,
            source_trace_complete=True,
            atom_coverage_sufficient=True,
            page_boundary_clear=True,
            identity_fit=True,
            source_supported=True,
            not_duplicate=True,
            relation_quality=True,
            synthesis_quality=True,
            maintainable=True,
            update_safe=True,
            write_safe=True,
        ),
    )


if __name__ == "__main__":
    unittest.main()
