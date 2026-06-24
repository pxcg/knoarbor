from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knoarbor.core.schemas.ingest_review import IngestDraftReview
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeAtomQualityReport
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan
from knoarbor.pipelines.ingest_context import IngestCandidatePageContext, IngestContextProvider
from knoarbor.pipelines.ingest_observer import IngestObserver
from knoarbor.pipelines.ingest_review_policy import IngestDraftReviewPolicy, auto_approve_ingest_draft_review
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


@dataclass(frozen=True)
class IngestSemanticExtraction:
    knowledge_extract: KnowledgeExtract
    source_digest: SourceDigest
    knowledge_atom_batch: KnowledgeAtomBatch
    knowledge_atom_quality: KnowledgeAtomQualityReport
    context_payload: dict[str, object]


class IngestSemanticRunner:
    """Runs the semantic ingest agent chain for one prepared source document."""

    def __init__(
        self,
        *,
        semantic_workflow: IngestSemanticWorkflow,
        context_provider: IngestContextProvider,
        review_policy: IngestDraftReviewPolicy | None = None,
    ) -> None:
        self.semantic_workflow = semantic_workflow
        self.context_provider = context_provider
        self.review_policy = review_policy or IngestDraftReviewPolicy()

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
        extraction = self.extract_source(
            document=document,
            max_tokens=max_tokens,
        )
        return self.plan_compile_review(
            vault_path=vault_path,
            knowledge_extract=extraction.knowledge_extract,
            source_digest=extraction.source_digest,
            knowledge_atom_batch=extraction.knowledge_atom_batch,
            knowledge_atom_quality=extraction.knowledge_atom_quality,
            index_payload=index_payload,
            source_file=source_file,
            max_tokens=max_tokens,
            history_start=history_start,
            extra_context=extraction.context_payload,
        )

    def extract_source(
        self,
        *,
        document: SourceDocument,
        max_tokens: int | None,
    ) -> IngestSemanticExtraction:
        observer = IngestObserver.current()
        observer.started("normalize_agent", message="Standardizing source document.", current_item=document.source_id)
        knowledge_extract = self.semantic_workflow.normalize(document, max_tokens=max_tokens)
        observer.finished(
            "normalize_agent",
            message="Source document standardized.",
            current_item=document.source_id,
            payload={"units": len(knowledge_extract.content_units), "source_title": knowledge_extract.source.title},
        )
        source_digest = build_source_digest_from_extract(knowledge_extract)
        observer.started("atom_agent", message="Extracting knowledge atoms.", current_item=source_digest.digest_id)
        knowledge_atom_batch = self.semantic_workflow.extract_atoms(
            source_digest,
            max_tokens=max_tokens,
        )
        knowledge_atom_quality = evaluate_knowledge_atoms(knowledge_atom_batch)
        observer.finished(
            "atom_agent",
            message="Knowledge atoms extracted.",
            current_item=source_digest.digest_id,
            payload={
                "source_digest_id": source_digest.digest_id,
                "summary": knowledge_atom_batch.summary(),
                "quality": knowledge_atom_quality.summary(),
            },
        )
        return IngestSemanticExtraction(
            knowledge_extract=knowledge_extract,
            source_digest=source_digest,
            knowledge_atom_batch=knowledge_atom_batch,
            knowledge_atom_quality=knowledge_atom_quality,
            context_payload={
                "source_digest": {
                    "digest_id": source_digest.digest_id,
                    "summary": source_digest.summary_counts(),
                },
                "knowledge_atoms": knowledge_atom_quality.summary(),
                "knowledge_atom_quality": knowledge_atom_quality.model_dump(),
            },
        )

    def plan_compile_review(
        self,
        *,
        vault_path: Path,
        knowledge_extract: KnowledgeExtract,
        source_digest: SourceDigest,
        knowledge_atom_batch: KnowledgeAtomBatch,
        knowledge_atom_quality: KnowledgeAtomQualityReport | None = None,
        index_payload: dict[str, object],
        source_file: str,
        max_tokens: int | None,
        history_start: int | None = None,
        extra_context: dict[str, object] | None = None,
    ) -> IngestSemanticRun:
        resolved_history_start = semantic_history_length(self.semantic_workflow) if history_start is None else history_start
        knowledge_atom_quality = knowledge_atom_quality or evaluate_knowledge_atoms(knowledge_atom_batch)
        observer = IngestObserver.current()
        observer.started(
            "retrieval",
            message="Retrieving related wiki context.",
            current_item=source_digest.digest_id,
        )
        wiki_context = self.context_provider.build(
            vault_path,
            knowledge_extract,
            knowledge_atom_batch=knowledge_atom_batch,
        )
        observer.finished(
            "retrieval",
            message=f"Retrieved {len(wiki_context.candidates)} candidate page(s).",
            current_item=source_digest.digest_id,
            payload={
                "mode": wiki_context.retrieval_mode,
                "query": wiki_context.query,
                "candidate_count": len(wiki_context.candidates),
                "warnings": wiki_context.warnings,
                "stats": wiki_context.stats,
            },
        )
        observer.started(
            "plan_agent",
            message="Planning wiki page operations.",
            current_item=source_digest.digest_id,
        )
        page_plan = self.semantic_workflow.plan_pages(
            knowledge_extract,
            source_digest=source_digest,
            knowledge_atom_batch=knowledge_atom_batch,
            existing_wiki_index=index_summary_payload(index_payload),
            wiki_context=wiki_context.model_dump(),
            max_tokens=max_tokens,
        )
        observer.finished(
            "plan_agent",
            message=f"Planned {len(page_plan.operations)} wiki operation(s).",
            current_item=source_digest.digest_id,
            payload={
                "operation_count": len(page_plan.operations),
                "actions": [operation.action for operation in page_plan.operations],
                "confidence": page_plan.confidence,
            },
        )
        if not has_executable_page_plan_operations(page_plan):
            semantic_metrics = summarize_semantic_runs(semantic_history_slice(self.semantic_workflow, resolved_history_start))
            candidate_page_context = IngestCandidatePageContext()
            return IngestSemanticRun(
                semantic_result=IngestSemanticWorkflowResult(
                    knowledge_extract=knowledge_extract,
                    source_digest=source_digest,
                    knowledge_atom_batch=knowledge_atom_batch,
                    knowledge_atom_quality=knowledge_atom_quality,
                    wiki_page_plan=page_plan,
                    wiki_draft_batch=empty_wiki_draft_batch(page_plan),
                    ingest_draft_review=empty_ingest_draft_review(page_plan),
                ),
                context_payload={
                    **(extra_context or {}),
                    "retrieval": {
                        "mode": wiki_context.retrieval_mode,
                        "query": wiki_context.query,
                        "candidate_count": len(wiki_context.candidates),
                        "warnings": wiki_context.warnings,
                        "stats": wiki_context.stats,
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
        observer.started(
            "draft_agent",
            message="Compiling wiki page drafts.",
            current_item=source_digest.digest_id,
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
        observer.finished(
            "draft_agent",
            message=f"Compiled {len(draft_batch.drafts)} draft(s).",
            current_item=source_digest.digest_id,
            payload={
                "draft_count": len(draft_batch.drafts),
                "drafts": [
                    {
                        "operation_index": draft.operation_index,
                        "write_action": draft.write_action,
                        "page_dir": draft.page_dir,
                        "title": draft.title,
                    }
                    for draft in draft_batch.drafts
                ],
            },
        )
        review_policy = self.review_policy.evaluate(
            page_plan=page_plan,
            draft_batch=draft_batch,
            atom_quality=knowledge_atom_quality,
        )
        if review_policy.should_review:
            observer.started(
                "review_agent",
                message="Reviewing high-risk draft batch.",
                current_item=source_digest.digest_id,
                payload=review_policy.as_context(),
            )
            review = self.semantic_workflow.review_drafts(
                knowledge_extract,
                page_plan,
                draft_batch,
                candidate_page_context=candidate_page_context.model_dump(),
                ingest_compile_context=ingest_compile_context,
                max_tokens=max_tokens,
            )
            observer.finished(
                "review_agent",
                message=f"Reviewed {len(review.decisions)} draft decision(s).",
                current_item=source_digest.digest_id,
                payload={"review_policy": review_policy.as_context(), "batch_decision": review.batch_decision},
            )
        else:
            review = auto_approve_ingest_draft_review(
                page_plan=page_plan,
                draft_batch=draft_batch,
                policy_decision=review_policy,
            )
            observer.skipped(
                "review_agent",
                message="Skipped semantic draft review for low-risk draft batch.",
                current_item=source_digest.digest_id,
                payload=review_policy.as_context(),
            )
        semantic_metrics = summarize_semantic_runs(semantic_history_slice(self.semantic_workflow, resolved_history_start))
        return IngestSemanticRun(
            semantic_result=IngestSemanticWorkflowResult(
                knowledge_extract=knowledge_extract,
                source_digest=source_digest,
                knowledge_atom_batch=knowledge_atom_batch,
                knowledge_atom_quality=knowledge_atom_quality,
                wiki_page_plan=page_plan,
                wiki_draft_batch=draft_batch,
                ingest_draft_review=review,
            ),
            context_payload={
                **(extra_context or {}),
                "retrieval": {
                    "mode": wiki_context.retrieval_mode,
                    "query": wiki_context.query,
                    "candidate_count": len(wiki_context.candidates),
                    "warnings": wiki_context.warnings,
                    "stats": wiki_context.stats,
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
                "review_policy": review_policy.as_context(),
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
