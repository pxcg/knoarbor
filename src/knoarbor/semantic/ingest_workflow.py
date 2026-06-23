from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from knoarbor.core.schemas.ingest_review import IngestDraftReview
from knoarbor.core.schemas.ingest_compile_context import IngestCompileContext
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan
from knoarbor.semantic.ingest_compile_context import build_ingest_compile_context
from knoarbor.semantic.runner import SemanticRunner
from knoarbor.semantic.source_digest import build_source_digest_from_extract
from knoarbor.semantic.source_normalize import build_source_normalize_input


class IngestSemanticWorkflowResult(BaseModel):
    knowledge_extract: KnowledgeExtract
    knowledge_atom_batch: KnowledgeAtomBatch | None = None
    wiki_page_plan: WikiPagePlan
    wiki_draft_batch: WikiDraftBatch
    ingest_draft_review: IngestDraftReview


class IngestSemanticWorkflow:
    """Run the semantic ingest chain without doing vault writes."""

    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    def run(
        self,
        document: SourceDocument,
        *,
        existing_wiki_index: dict[str, Any] | None = None,
        wiki_context: dict[str, Any] | None = None,
        candidate_page_context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> IngestSemanticWorkflowResult:
        knowledge_extract = self.normalize(document, max_tokens=max_tokens)
        source_digest = build_source_digest_from_extract(knowledge_extract)
        knowledge_atom_batch = self.extract_atoms(
            source_digest,
            knowledge_extract=knowledge_extract,
            max_tokens=max_tokens,
        )
        wiki_page_plan = self.plan_pages(
            knowledge_extract,
            knowledge_atom_batch=knowledge_atom_batch,
            existing_wiki_index=existing_wiki_index,
            wiki_context=wiki_context,
            max_tokens=max_tokens,
        )
        wiki_draft_batch = self.compile_drafts(
            knowledge_extract,
            wiki_page_plan,
            knowledge_atom_batch=knowledge_atom_batch,
            candidate_page_context=candidate_page_context,
            max_tokens=max_tokens,
        )
        ingest_draft_review = self.review_drafts(
            knowledge_extract,
            wiki_page_plan,
            wiki_draft_batch,
            candidate_page_context=candidate_page_context,
            max_tokens=max_tokens,
        )
        return IngestSemanticWorkflowResult(
            knowledge_extract=knowledge_extract,
            knowledge_atom_batch=knowledge_atom_batch,
            wiki_page_plan=wiki_page_plan,
            wiki_draft_batch=wiki_draft_batch,
            ingest_draft_review=ingest_draft_review,
        )

    def normalize(self, document: SourceDocument, *, max_tokens: int | None = None) -> KnowledgeExtract:
        result = self.runner.run(
            "source_normalize",
            build_source_normalize_input(document),
            max_tokens=max_tokens,
        )
        return _expect_output(result.output, KnowledgeExtract)

    def extract_atoms(
        self,
        source_digest: SourceDigest,
        *,
        knowledge_extract: KnowledgeExtract | None = None,
        max_tokens: int | None = None,
    ) -> KnowledgeAtomBatch:
        result = self.runner.run(
            "wiki_atom_extract",
            {
                "source_digest": source_digest.model_dump(),
                "knowledge_extract": knowledge_extract.model_dump() if knowledge_extract else {},
            },
            max_tokens=max_tokens,
        )
        return _expect_output(result.output, KnowledgeAtomBatch)

    def plan_pages(
        self,
        knowledge_extract: KnowledgeExtract,
        *,
        knowledge_atom_batch: KnowledgeAtomBatch | None = None,
        existing_wiki_index: dict[str, Any] | None = None,
        wiki_context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> WikiPagePlan:
        result = self.runner.run(
            "wiki_page_plan",
            {
                "knowledge_extract": knowledge_extract.model_dump(),
                "knowledge_atoms": knowledge_atom_batch.model_dump() if knowledge_atom_batch else {},
                "existing_wiki_index": existing_wiki_index or {},
                "wiki_context": wiki_context or {},
            },
            max_tokens=max_tokens,
        )
        return _expect_output(result.output, WikiPagePlan)

    def compile_drafts(
        self,
        knowledge_extract: KnowledgeExtract,
        wiki_page_plan: WikiPagePlan,
        *,
        knowledge_atom_batch: KnowledgeAtomBatch | None = None,
        candidate_page_context: dict[str, Any] | None = None,
        ingest_compile_context: IngestCompileContext | dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> WikiDraftBatch:
        actionable_operations = [
            operation.model_dump()
            for operation in wiki_page_plan.operations
            if operation.action != "skip"
        ]
        compile_context = _compile_context_payload(
            knowledge_extract,
            wiki_page_plan,
            candidate_page_context,
            ingest_compile_context,
        )
        result = self.runner.run(
            "wiki_draft_compile",
            {
                "knowledge_extract": knowledge_extract.model_dump(),
                "knowledge_atoms": knowledge_atom_batch.model_dump() if knowledge_atom_batch else {},
                "wiki_page_plan": wiki_page_plan.model_dump(),
                "wiki_operations": actionable_operations,
                "ingest_compile_context": compile_context,
                "candidate_page_context": candidate_page_context or {},
            },
            max_tokens=max_tokens,
        )
        draft_batch = _expect_output(result.output, WikiDraftBatch)
        return _with_runtime_model_metadata(draft_batch, provider=result.provider, model=result.model)

    def review_drafts(
        self,
        knowledge_extract: KnowledgeExtract,
        wiki_page_plan: WikiPagePlan,
        wiki_draft_batch: WikiDraftBatch,
        *,
        candidate_page_context: dict[str, Any] | None = None,
        ingest_compile_context: IngestCompileContext | dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> IngestDraftReview:
        compile_context = _compile_context_payload(
            knowledge_extract,
            wiki_page_plan,
            candidate_page_context,
            ingest_compile_context,
        )
        result = self.runner.run(
            "ingest_draft_review",
            {
                "knowledge_extract": knowledge_extract.model_dump(),
                "wiki_page_plan": wiki_page_plan.model_dump(),
                "wiki_draft_batch": wiki_draft_batch.model_dump(),
                "ingest_compile_context": compile_context,
                "candidate_page_context": candidate_page_context or {},
            },
            max_tokens=max_tokens,
        )
        return _expect_output(result.output, IngestDraftReview)


def _expect_output(value: BaseModel, expected_type: type[Any]) -> Any:
    if not isinstance(value, expected_type):
        raise TypeError(f"Expected {expected_type.__name__}, got {type(value).__name__}")
    return value


def _with_runtime_model_metadata(batch: WikiDraftBatch, *, provider: str, model: str) -> WikiDraftBatch:
    """Model identity is runtime metadata, not an LLM-authored page fact."""
    for draft in batch.drafts:
        draft.model_provider = provider
        draft.model_name = model
    return batch


def _compile_context_payload(
    knowledge_extract: KnowledgeExtract,
    wiki_page_plan: WikiPagePlan,
    candidate_page_context: dict[str, Any] | None,
    ingest_compile_context: IngestCompileContext | dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(ingest_compile_context, IngestCompileContext):
        return ingest_compile_context.model_dump()
    if isinstance(ingest_compile_context, dict) and ingest_compile_context:
        return ingest_compile_context
    return build_ingest_compile_context(
        knowledge_extract,
        wiki_page_plan,
        candidate_page_context,
    ).model_dump()
