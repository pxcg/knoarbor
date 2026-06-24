from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from knoarbor.core.schemas.ingest_review import IngestDraftReview
from knoarbor.core.schemas.ingest_compile_context import IngestCompileContext
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeAtomQualityReport
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan
from knoarbor.core.source_unitization import apply_source_units_to_extract
from knoarbor.semantic.ingest_compile_context import build_ingest_compile_context
from knoarbor.semantic.knowledge_atom_normalization import normalize_knowledge_atom_batch
from knoarbor.semantic.knowledge_atom_closure import close_plan_atoms
from knoarbor.semantic.knowledge_atom_quality import evaluate_knowledge_atoms
from knoarbor.semantic.page_assembly import build_page_assembly_payload
from knoarbor.semantic.page_projection import project_draft_batch_from_page_assembly
from knoarbor.semantic.runner import SemanticRunner
from knoarbor.semantic.source_digest import build_source_digest_from_extract
from knoarbor.semantic.source_digest_drafts import build_source_digest_drafts_from_plan
from knoarbor.semantic.source_normalize import build_source_normalize_input


class IngestSemanticWorkflowResult(BaseModel):
    knowledge_extract: KnowledgeExtract
    source_digest: SourceDigest
    knowledge_atom_batch: KnowledgeAtomBatch | None = None
    knowledge_atom_quality: KnowledgeAtomQualityReport | None = None
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
            max_tokens=max_tokens,
        )
        knowledge_atom_quality = self.validate_atoms(knowledge_atom_batch)
        wiki_page_plan = self.plan_pages(
            knowledge_extract,
            source_digest=source_digest,
            knowledge_atom_batch=knowledge_atom_batch,
            existing_wiki_index=existing_wiki_index,
            wiki_context=wiki_context,
            max_tokens=max_tokens,
        )
        wiki_draft_batch = self.compile_drafts(
            knowledge_extract,
            wiki_page_plan,
            source_digest=source_digest,
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
            source_digest=source_digest,
            knowledge_atom_batch=knowledge_atom_batch,
            knowledge_atom_quality=knowledge_atom_quality,
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
        return apply_source_units_to_extract(document, _expect_output(result.output, KnowledgeExtract))

    def extract_atoms(
        self,
        source_digest: SourceDigest,
        *,
        max_tokens: int | None = None,
    ) -> KnowledgeAtomBatch:
        result = self.runner.run(
            "wiki_atom_extract",
            {"source_digest": source_digest.model_dump()},
            max_tokens=max_tokens,
        )
        return normalize_knowledge_atom_batch(_expect_output(result.output, KnowledgeAtomBatch))

    def validate_atoms(self, knowledge_atom_batch: KnowledgeAtomBatch) -> KnowledgeAtomQualityReport:
        return evaluate_knowledge_atoms(knowledge_atom_batch)

    def plan_pages(
        self,
        knowledge_extract: KnowledgeExtract,
        *,
        source_digest: SourceDigest | None = None,
        knowledge_atom_batch: KnowledgeAtomBatch | None = None,
        existing_wiki_index: dict[str, Any] | None = None,
        wiki_context: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> WikiPagePlan:
        resolved_source_digest = source_digest or build_source_digest_from_extract(knowledge_extract)
        result = self.runner.run(
            "wiki_page_plan",
            {
                "source_digest": _source_digest_plan_payload(resolved_source_digest),
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
        source_digest: SourceDigest | None = None,
        knowledge_atom_batch: KnowledgeAtomBatch | None = None,
        candidate_page_context: dict[str, Any] | None = None,
        ingest_compile_context: IngestCompileContext | dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> WikiDraftBatch:
        resolved_source_digest = source_digest or build_source_digest_from_extract(knowledge_extract)
        source_drafts = build_source_digest_drafts_from_plan(wiki_page_plan, resolved_source_digest)
        page_assembly = _without_source_digest_assembly(
            build_page_assembly_payload(
                knowledge_atom_batch,
                wiki_page_plan,
            )
        )
        if not _has_non_source_actionable_operations(wiki_page_plan):
            return WikiDraftBatch(
                drafts=source_drafts,
                batch_summary="Generated source digest audit draft(s) deterministically.",
                warnings=["wiki_draft_compile skipped because the plan contains only source digest audit operations."],
            )
        compile_context = _compile_context_payload(
            knowledge_extract,
            wiki_page_plan,
            candidate_page_context,
            ingest_compile_context,
        )
        compile_context = _without_source_digest_compile_operations(compile_context)
        result = self.runner.run(
            "wiki_draft_compile",
            {
                "knowledge_atoms": _selected_knowledge_atoms_for_plan(
                    knowledge_atom_batch,
                    wiki_page_plan,
                ),
                "page_assembly": page_assembly,
                "ingest_compile_context": _model_compile_context_payload(compile_context),
            },
            max_tokens=max_tokens,
        )
        draft_batch = _expect_output(result.output, WikiDraftBatch)
        draft_batch = _with_runtime_model_metadata(draft_batch, provider=result.provider, model=result.model)
        projected = project_draft_batch_from_page_assembly(
            draft_batch,
            page_assembly,
            wiki_page_plan,
            resolved_source_digest,
        )
        return _merge_draft_batches(
            source_drafts,
            projected,
            batch_summary=projected.batch_summary,
        )

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
                "wiki_draft_batch": wiki_draft_batch.model_dump(),
                "ingest_compile_context": _model_compile_context_payload(compile_context),
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


def _without_source_digest_assembly(page_assembly: dict[str, object]) -> dict[str, object]:
    payload = deepcopy(page_assembly)
    operations = payload.get("operations")
    if isinstance(operations, list):
        payload["operations"] = [
            operation for operation in operations
            if not (isinstance(operation, dict) and operation.get("page_dir") == "sources")
        ]
    return payload


def _has_non_source_actionable_operations(page_plan: WikiPagePlan) -> bool:
    return any(operation.action != "skip" and operation.page_dir != "sources" for operation in page_plan.operations)


def _without_source_digest_compile_operations(compile_context: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(compile_context)
    operations = payload.get("operations")
    if isinstance(operations, list):
        payload["operations"] = [
            operation for operation in operations
            if not (isinstance(operation, dict) and operation.get("page_dir") == "sources")
        ]
    return payload


def _merge_draft_batches(
    source_drafts: list[WikiDraftBatchItem],
    model_batch: WikiDraftBatch,
    *,
    batch_summary: str,
) -> WikiDraftBatch:
    drafts = [*source_drafts, *model_batch.drafts]
    drafts.sort(key=lambda draft: draft.operation_index)
    warnings = list(model_batch.warnings)
    if source_drafts:
        warnings.append("Source digest audit draft(s) were generated deterministically outside wiki_draft_compile.")
    return WikiDraftBatch(drafts=drafts, batch_summary=batch_summary, warnings=warnings)


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


def _model_compile_context_payload(compile_context: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(compile_context)
    current_content = payload.get("current_content")
    if not isinstance(current_content, dict):
        return payload
    primary_content = current_content.get("primary_content")
    if isinstance(primary_content, str) and primary_content:
        current_content["primary_content"] = ""
        current_content["source_text_policy"] = "omitted_after_atom_extraction"
        current_content["source_text_note"] = (
            "Full source text was used during normalize and atom extraction. "
            "Use selected knowledge_atoms evidence excerpts for draft and review."
        )
    return payload


def _source_digest_plan_payload(source_digest: SourceDigest) -> dict[str, Any]:
    return {
        "schema_version": source_digest.schema_version,
        "digest_id": source_digest.digest_id,
        "source": source_digest.source.model_dump(),
        "raw_source": source_digest.raw_source,
        "content_hash": source_digest.content_hash,
        "source_focus": source_digest.source_focus,
        "summary": source_digest.summary,
        "units": [
            {
                "index": unit.index,
                "unit_type": unit.unit_type,
                "title": unit.title,
                "summary": unit.summary,
                "source_unit_index": unit.evidence.source_unit_index,
                "excerpt_hash": unit.evidence.excerpt_hash,
                "metadata": dict(unit.metadata),
            }
            for unit in source_digest.units
        ],
        "contribution_map": [item.model_dump() for item in source_digest.contribution_map],
        "unresolved_items": [item.model_dump() for item in source_digest.unresolved_items],
        "confidence": source_digest.confidence,
        "warnings": list(source_digest.warnings),
    }


def _selected_knowledge_atoms_for_plan(
    knowledge_atom_batch: KnowledgeAtomBatch | None,
    wiki_page_plan: WikiPagePlan,
) -> dict[str, Any]:
    selected_batch = close_plan_atoms(knowledge_atom_batch, wiki_page_plan)
    if selected_batch is None:
        return {}
    return selected_batch.model_dump()
