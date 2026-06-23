from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knoarbor.core.schemas.ingest_review import IngestDraftReview
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan
from knoarbor.pipelines.ingest_context import IngestCandidatePageContext, IngestContextProvider
from knoarbor.semantic.ingest_compile_context import build_ingest_compile_context
from knoarbor.semantic.ingest_workflow import IngestSemanticWorkflow, IngestSemanticWorkflowResult
from knoarbor.semantic.knowledge_atom_quality import evaluate_knowledge_atoms
from knoarbor.semantic.metrics import summarize_semantic_runs
from knoarbor.semantic.source_digest import build_source_digest_from_extract


@dataclass(frozen=True)
class IngestSemanticRun:
    semantic_result: IngestSemanticWorkflowResult
    context_payload: dict[str, object]
    candidate_page_context: IngestCandidatePageContext


class IngestSemanticRunner:
    """Runs the semantic ingest agent chain for one prepared source document."""

    def __init__(
        self,
        *,
        semantic_workflow: IngestSemanticWorkflow,
        context_provider: IngestContextProvider,
    ) -> None:
        self.semantic_workflow = semantic_workflow
        self.context_provider = context_provider

    def run(
        self,
        *,
        vault_path: Path,
        document: SourceDocument,
        index_payload: dict[str, object],
        source_file: str,
        max_tokens: int | None,
    ) -> IngestSemanticRun:
        history_start = semantic_history_length(self.semantic_workflow)
        knowledge_extract = self.semantic_workflow.normalize(document, max_tokens=max_tokens)
        source_digest = build_source_digest_from_extract(knowledge_extract)
        knowledge_atom_batch = self.semantic_workflow.extract_atoms(
            source_digest,
            knowledge_extract=knowledge_extract,
            max_tokens=max_tokens,
        )
        knowledge_atom_quality = evaluate_knowledge_atoms(knowledge_atom_batch)
        wiki_context = self.context_provider.build(
            vault_path,
            knowledge_extract,
            knowledge_atom_batch=knowledge_atom_batch,
        )
        page_plan = self.semantic_workflow.plan_pages(
            knowledge_extract,
            source_digest=source_digest,
            knowledge_atom_batch=knowledge_atom_batch,
            existing_wiki_index=index_summary_payload(index_payload),
            wiki_context=wiki_context.model_dump(),
            max_tokens=max_tokens,
        )
        if not has_executable_page_plan_operations(page_plan):
            semantic_metrics = summarize_semantic_runs(semantic_history_slice(self.semantic_workflow, history_start))
            candidate_page_context = IngestCandidatePageContext()
            return IngestSemanticRun(
                semantic_result=IngestSemanticWorkflowResult(
                    knowledge_extract=knowledge_extract,
                    knowledge_atom_batch=knowledge_atom_batch,
                    wiki_page_plan=page_plan,
                    wiki_draft_batch=empty_wiki_draft_batch(page_plan),
                    ingest_draft_review=empty_ingest_draft_review(page_plan),
                ),
                context_payload={
                    "retrieval": {
                        "mode": wiki_context.retrieval_mode,
                        "query": wiki_context.query,
                        "candidate_count": len(wiki_context.candidates),
                        "warnings": wiki_context.warnings,
                        "stats": wiki_context.stats,
                    },
                    "source_digest": {
                        "digest_id": source_digest.digest_id,
                        "summary": source_digest.summary_counts(),
                    },
                    "knowledge_atoms": knowledge_atom_quality.summary(),
                    "knowledge_atom_quality": knowledge_atom_quality.model_dump(),
                    "materialized_pages": candidate_page_context.stats,
                    "semantic_metrics": semantic_metrics,
                    "short_circuit": {
                        "stage": "page_plan",
                        "reason": semantic_page_plan_skip_reason(page_plan),
                    },
                },
                candidate_page_context=candidate_page_context,
            )

        candidate_page_context = self.context_provider.materialize(vault_path, page_plan)
        ingest_compile_context = build_ingest_compile_context(
            knowledge_extract,
            page_plan,
            candidate_page_context.model_dump(),
        )
        draft_batch = self.semantic_workflow.compile_drafts(
            knowledge_extract,
            page_plan,
            knowledge_atom_batch=knowledge_atom_batch,
            candidate_page_context=candidate_page_context.model_dump(),
            ingest_compile_context=ingest_compile_context,
            max_tokens=max_tokens,
        )
        draft_batch = materialize_draft_source_files(draft_batch, source_file)
        review = self.semantic_workflow.review_drafts(
            knowledge_extract,
            page_plan,
            draft_batch,
            candidate_page_context=candidate_page_context.model_dump(),
            ingest_compile_context=ingest_compile_context,
            max_tokens=max_tokens,
        )
        semantic_metrics = summarize_semantic_runs(semantic_history_slice(self.semantic_workflow, history_start))
        return IngestSemanticRun(
            semantic_result=IngestSemanticWorkflowResult(
                knowledge_extract=knowledge_extract,
                knowledge_atom_batch=knowledge_atom_batch,
                wiki_page_plan=page_plan,
                wiki_draft_batch=draft_batch,
                ingest_draft_review=review,
            ),
            context_payload={
                "retrieval": {
                    "mode": wiki_context.retrieval_mode,
                    "query": wiki_context.query,
                    "candidate_count": len(wiki_context.candidates),
                    "warnings": wiki_context.warnings,
                    "stats": wiki_context.stats,
                },
                "source_digest": {
                    "digest_id": source_digest.digest_id,
                    "summary": source_digest.summary_counts(),
                },
                "knowledge_atoms": knowledge_atom_quality.summary(),
                "knowledge_atom_quality": knowledge_atom_quality.model_dump(),
                "materialized_pages": candidate_page_context.stats,
                "compile_context": {
                    "context_policy": ingest_compile_context.context_policy,
                    "target_pages": len(ingest_compile_context.page_context.targets),
                    "related_pages": len(ingest_compile_context.page_context.related),
                    "candidate_pages": len(ingest_compile_context.page_context.candidates),
                },
                "semantic_metrics": semantic_metrics,
            },
            candidate_page_context=candidate_page_context,
        )


def has_executable_page_plan_operations(page_plan: WikiPagePlan) -> bool:
    return any(operation.action in {"create", "update"} for operation in page_plan.operations)


def empty_wiki_draft_batch(page_plan: WikiPagePlan) -> WikiDraftBatch:
    return WikiDraftBatch(
        drafts=[],
        batch_summary=semantic_page_plan_skip_reason(page_plan),
        warnings=list(page_plan.warnings),
    )


def empty_ingest_draft_review(page_plan: WikiPagePlan) -> IngestDraftReview:
    return IngestDraftReview(
        decisions=[],
        batch_decision="reject",
        summary=semantic_page_plan_skip_reason(page_plan),
        warnings=list(page_plan.warnings),
    )


def semantic_page_plan_skip_reason(page_plan: WikiPagePlan) -> str:
    operations = page_plan.operations
    if not operations:
        return "Page plan contains no executable operations."
    skip_reasons = [operation.decision_reason for operation in operations if operation.action == "skip" and operation.decision_reason]
    return skip_reasons[0] if skip_reasons else "Page plan contains no executable operations."


def materialize_draft_source_files(draft_batch: WikiDraftBatch, source_file: str) -> WikiDraftBatch:
    drafts = [
        draft.model_copy(update={"source_file": source_file})
        for draft in draft_batch.drafts
    ]
    return draft_batch.model_copy(update={"drafts": drafts})


def semantic_history_length(semantic_workflow: object) -> int:
    runner = getattr(semantic_workflow, "runner", None)
    history = getattr(runner, "history", None)
    return len(history) if isinstance(history, list) else 0


def semantic_history_slice(semantic_workflow: object, start: int) -> list[object]:
    runner = getattr(semantic_workflow, "runner", None)
    history = getattr(runner, "history", None)
    return history[start:] if isinstance(history, list) else []


def index_summary_payload(index_payload: dict[str, object]) -> dict[str, object]:
    content = index_payload.get("content")
    return {
        "available": bool(index_payload.get("available")),
        "path": index_payload.get("path", ".knoarbor/index/manifest.json"),
        "content_length": len(content) if isinstance(content, str) else 0,
        "note": "Ingest uses wiki_context.candidates as the authoritative lightweight candidate pool; full index content is not duplicated in the model input.",
    }
