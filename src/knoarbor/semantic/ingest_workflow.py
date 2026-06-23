from __future__ import annotations

from copy import deepcopy
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
            source_digest=source_digest,
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
        knowledge_atom_batch: KnowledgeAtomBatch | None = None,
        candidate_page_context: dict[str, Any] | None = None,
        ingest_compile_context: IngestCompileContext | dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> WikiDraftBatch:
        compile_context = _compile_context_payload(
            knowledge_extract,
            wiki_page_plan,
            candidate_page_context,
            ingest_compile_context,
        )
        result = self.runner.run(
            "wiki_draft_compile",
            {
                "knowledge_atoms": _selected_knowledge_atoms_for_plan(
                    knowledge_atom_batch,
                    wiki_page_plan,
                ),
                "ingest_compile_context": _model_compile_context_payload(compile_context),
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
        "observations": [
            {
                "id": observation.id,
                "observation_type": observation.observation_type,
                "statement": observation.statement,
                "confidence": observation.confidence,
            }
            for observation in source_digest.observations
        ],
        "mentioned_objects": [item.model_dump() for item in source_digest.mentioned_objects],
        "limitations": list(source_digest.limitations),
        "confidence": source_digest.confidence,
        "warnings": list(source_digest.warnings),
    }


def _selected_knowledge_atoms_for_plan(
    knowledge_atom_batch: KnowledgeAtomBatch | None,
    wiki_page_plan: WikiPagePlan,
) -> dict[str, Any]:
    if knowledge_atom_batch is None:
        return {}

    selected_claim_ids: set[str] = set()
    selected_relation_ids: set[str] = set()
    for operation in wiki_page_plan.operations:
        if operation.action == "skip":
            continue
        selected_claim_ids.update(operation.selected_claim_ids)
        selected_relation_ids.update(operation.selected_relation_ids)

    relations_by_id = {relation.id: relation for relation in knowledge_atom_batch.relations}

    for relation_id in list(selected_relation_ids):
        relation = relations_by_id.get(relation_id)
        if relation is None:
            continue
        selected_claim_ids.update(relation.source_claim_ids)

    selected_batch = KnowledgeAtomBatch(
        source_digest_id=knowledge_atom_batch.source_digest_id,
        claims=[claim for claim in knowledge_atom_batch.claims if claim.id in selected_claim_ids],
        relations=[relation for relation in knowledge_atom_batch.relations if relation.id in selected_relation_ids],
        warnings=list(knowledge_atom_batch.warnings),
    )
    selected_entity_names = {
        entity_name.casefold()
        for claim in selected_batch.claims
        for entity_name in claim.entity_names
    }
    for relation in selected_batch.relations:
        selected_entity_names.add(relation.subject.name.casefold())
        selected_entity_names.add(relation.object.name.casefold())
    selected_batch.entities = [
        entity
        for entity in knowledge_atom_batch.entities
        if entity.name.casefold() in selected_entity_names or (entity.atom_id and entity.atom_id in selected_claim_ids | selected_relation_ids)
    ]
    selected_evidence_keys = {
        _knowledge_evidence_key(span)
        for claim in selected_batch.claims
        for span in claim.evidence
    }
    selected_evidence_keys.update(
        _knowledge_evidence_key(span)
        for relation in selected_batch.relations
        for span in relation.evidence
    )
    selected_batch.evidence = [
        span
        for span in knowledge_atom_batch.evidence
        if _knowledge_evidence_key(span) in selected_evidence_keys
    ]
    return selected_batch.model_dump()


def _knowledge_evidence_key(span: Any) -> tuple[str, int | None, str]:
    return (span.source_digest_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
