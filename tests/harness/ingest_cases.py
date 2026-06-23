from __future__ import annotations

import json

from knoarbor.core.schemas.ingest_review import (
    IngestDraftReview,
    IngestDraftReviewDecision,
    IngestReviewChecks,
    IngestReviewDimensionScores,
)
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.knowledge_extract import CompileContext, ContentUnit, KnowledgeExtract, KnowledgeSource
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan


def long_markdown_text() -> str:
    sections = [
        ("Agent Loop Overview", "Agent loops coordinate observe, reason, act, and feedback."),
        ("Workflow Boundaries", "Workflows constrain agent behavior with deterministic execution boundaries."),
        ("Evaluation Harness", "Golden fixtures keep prompt, schema, and report behavior reviewable."),
    ]
    return "\n\n".join(
        f"## {title}\n\n" + "\n".join(f"{sentence} Example {index:02d}." for index in range(18))
        for title, sentence in sections
    )


def codex_chat_payload() -> dict[str, object]:
    turns = []
    for turn_index, topic in enumerate(["agent loop", "workflow boundary", "golden harness"]):
        turns.append(
            {
                "raw_index": turn_index * 2,
                "role": "user",
                "content": f"Explain {topic} for KnoArbor.",
            }
        )
        turns.append(
            {
                "raw_index": turn_index * 2 + 1,
                "role": "assistant",
                "content": " ".join(
                    [
                        f"{topic} keeps the system structured and auditable.",
                        "It should remain grounded in source evidence.",
                    ]
                    * 14
                ),
            }
        )
    return {"session_id": "codex-golden-session", "turns": turns}


def long_markdown_source_document() -> SourceDocument:
    return SourceDocument(
        source_id="markdown:golden-long-note",
        source_type="markdown",
        origin=SourceOrigin(connector="markdown", uri="file:///raw/notes/long-agent-loop.md", raw_path="raw/notes/long-agent-loop.md"),
        content=SourceContent(format="markdown", text=long_markdown_text()),
        metadata={"title": "Long Agent Loop Note"},
        fingerprint=SourceFingerprint(content_hash="golden-long-note", connector_version="markdown@1"),
    )


def codex_chat_source_document() -> SourceDocument:
    return SourceDocument(
        source_id="codex:golden-session",
        source_type="codex_chat",
        origin=SourceOrigin(connector="codex", uri="file:///raw/chats/codex-golden-session.json", raw_path="raw/chats/codex-golden-session.json"),
        content=SourceContent(format="json", text=json.dumps(codex_chat_payload(), ensure_ascii=False, indent=2)),
        metadata={"title": "Codex Golden Session"},
        fingerprint=SourceFingerprint(content_hash="golden-codex-session", connector_version="codex@1"),
    )


class SourceDigestOnlyWorkflow:
    """Stable semantic workflow for ingest harness tests.

    It models the segment extraction contract without calling a real model.
    Segments only produce normalized extracts and atom batches; page planning
    runs once after deterministic source-level aggregation.
    """

    def __init__(self) -> None:
        self.calls = 0

    def normalize(self, document: SourceDocument, **_: object) -> KnowledgeExtract:
        self.calls += 1
        title = str(document.metadata.get("segmentation", {}).get("segment_title") or document.metadata.get("title") or "Source")
        return KnowledgeExtract(
            source=KnowledgeSource(
                source_type=document.source_type,
                source_app=document.origin.connector,
                source_id=document.source_id,
                source_path=document.origin.raw_path,
                title=title,
            ),
            content_units=[
                ContentUnit(index=0, unit_type="note", role="note", title=title, content=document.content.text),
            ],
            compile_context=CompileContext(primary_content=document.content.text[:1200]),
            confidence=0.9,
            warnings=[],
        )

    def extract_atoms(self, source_digest, **_: object) -> KnowledgeAtomBatch:
        return KnowledgeAtomBatch(source_digest_id=source_digest.digest_id)

    def plan_pages(self, knowledge_extract: KnowledgeExtract, **kwargs: object) -> WikiPagePlan:
        source_digest_id = kwargs["knowledge_atom_batch"].source_digest_id  # type: ignore[index,union-attr]
        return WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action="create",
                    page_dir="sources",
                    title="Long Source Digest",
                    knowledge_object="Long source provenance",
                    source_digest_ids=[source_digest_id],
                    decision_reason="Create one digest for the source, not one page per segment.",
                )
            ],
            overall_summary="Create one source digest.",
            confidence=0.9,
            warnings=[],
        )

    def compile_drafts(
        self,
        knowledge_extract: KnowledgeExtract,
        wiki_page_plan: WikiPagePlan,
        **kwargs: object,
    ) -> WikiDraftBatch:
        source_digest_id = kwargs["knowledge_atom_batch"].source_digest_id  # type: ignore[index,union-attr]
        return WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action="create",
                    title="Long Source Digest",
                    page_dir="sources",
                    question="Long source",
                    answer=f"Segment evidence: {knowledge_extract.compile_context.primary_content[:80]}",
                    summary="Digest for a long source processed through segmentation.",
                    claims=["C1: Source segmentation aggregates multiple source segments into one source digest."],
                    entities=["[[Source Segmentation]]", "[[Long Source Digest]]"],
                    relations=["[[Source Segmentation]] | produces | [[Long Source Digest]] | C1"],
                    evidence=[f"C1 | {source_digest_id} | segment:{knowledge_extract.source.title} | segmented source content supports this digest | high"],
                    synthesis="The source digest preserves segmented source provenance without creating duplicate source pages.",
                    key_points=["Segment evidence is aggregated before writing."],
                    tags=["source", "segmentation"],
                    source_digest_ids=[source_digest_id],
                    confidence=0.9,
                    model_provider="scripted",
                    model_name="ingest-harness",
                )
            ],
            batch_summary="One source digest draft.",
            warnings=[],
        )

    def review_drafts(
        self,
        knowledge_extract: KnowledgeExtract,
        wiki_page_plan: WikiPagePlan,
        wiki_draft_batch: WikiDraftBatch,
        **_: object,
    ) -> IngestDraftReview:
        return IngestDraftReview(
            decisions=[
                IngestDraftReviewDecision(
                    operation_index=0,
                    decision="approve",
                    quality_score=0.92,
                    risk_level="low",
                    write_safety="safe_create",
                    reason="Source digest is supported and safe to create.",
                    required_changes=[],
                    dimension_scores=IngestReviewDimensionScores(
                        source_trace=0.9,
                        atom_coverage=0.9,
                        source_support=0.92,
                        page_boundary=0.9,
                        identity_fit=0.95,
                        duplication_risk=0.9,
                        relation_quality=0.9,
                        synthesis_quality=0.88,
                        maintainability=0.9,
                        update_safety=0.95,
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
            ],
            batch_decision="approve",
            summary="Approved source digest.",
            warnings=[],
        )


class MultiObjectSegmentWorkflow:
    """Stable workflow for long-source ingest quality snapshots.

    Unlike `SourceDigestOnlyWorkflow`, this fixture emits one source digest plus
    durable knowledge pages from the aggregated source. It keeps the model
    behavior deterministic while exercising the page-boundary, report, and
    write surfaces that matter for long notes and long chat sessions.
    """

    def __init__(self) -> None:
        self.calls = 0

    def normalize(self, document: SourceDocument, **_: object) -> KnowledgeExtract:
        self.calls += 1
        segment = _segment_metadata(document)
        title = segment.get("segment_title") or document.metadata.get("title") or "Source"
        return KnowledgeExtract(
            source=KnowledgeSource(
                source_type=_knowledge_source_type(document),
                source_app=document.origin.connector,
                source_id=document.source_id,
                source_path=document.origin.raw_path,
                title=str(title),
            ),
            content_units=[
                ContentUnit(
                    index=0,
                    unit_type="section",
                    role="note",
                    title=str(title),
                    content=document.content.text,
                )
            ],
            compile_context=CompileContext(primary_content=document.content.text[:1200]),
            confidence=0.9,
            warnings=[],
        )

    def extract_atoms(self, source_digest, **_: object) -> KnowledgeAtomBatch:
        return KnowledgeAtomBatch(source_digest_id=source_digest.digest_id)

    def plan_pages(self, knowledge_extract: KnowledgeExtract, **kwargs: object) -> WikiPagePlan:
        topic = _topic_for_extract(knowledge_extract)
        source_digest_id = kwargs["knowledge_atom_batch"].source_digest_id  # type: ignore[index,union-attr]
        atom_id = f"claim_{topic['title'].lower().replace(' ', '_').replace('-', '_')}"
        return WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action="create",
                    page_dir="sources",
                    title=f"{_source_label(knowledge_extract)} Source Digest",
                    knowledge_object=f"{_source_label(knowledge_extract)} provenance",
                    source_digest_ids=[source_digest_id],
                    decision_reason="One source digest represents the whole source across segments.",
                ),
                WikiPageOperation(
                    action="create",
                    page_dir=topic["page_dir"],
                    title=topic["title"],
                    knowledge_object=topic["knowledge_object"],
                    selected_claim_ids=[atom_id],
                    source_digest_ids=[source_digest_id],
                    decision_reason=topic["decision_reason"],
                ),
            ],
            overall_summary="Create source provenance and one stable knowledge page for the current segment.",
            confidence=0.9,
            warnings=[],
        )

    def compile_drafts(
        self,
        knowledge_extract: KnowledgeExtract,
        wiki_page_plan: WikiPagePlan,
        **kwargs: object,
    ) -> WikiDraftBatch:
        topic = _topic_for_extract(knowledge_extract)
        source_label = _source_label(knowledge_extract)
        segment_title = knowledge_extract.source.title or "Segment"
        source_digest_id = kwargs["knowledge_atom_batch"].source_digest_id  # type: ignore[index,union-attr]
        atom_id = f"claim_{topic['title'].lower().replace(' ', '_').replace('-', '_')}"
        return WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action="create",
                    title=f"{source_label} Source Digest",
                    page_dir="sources",
                    question=f"Source segment: {segment_title}",
                    answer=f"Evidence from segment `{segment_title}`: {knowledge_extract.compile_context.primary_content[:160]}",
                    summary=f"Source digest for {source_label}, aggregated from segmented ingest.",
                    claims=[f"C1: {source_label} contains segment evidence for {segment_title}."],
                    entities=[f"[[{source_label}]]", f"[[{segment_title}]]"],
                    relations=[f"[[{source_label}]] | contains_segment | [[{segment_title}]] | C1"],
                    evidence=[f"C1 | {source_digest_id} | segment:{segment_title} | source segment supports this digest entry | high"],
                    synthesis=f"{source_label} source digest keeps provenance for segment {segment_title}.",
                    key_points=[f"Includes evidence from {segment_title}."],
                    tags=["source", "segmented-ingest", source_label.lower().replace(" ", "-")],
                    source_digest_ids=[source_digest_id],
                    confidence=0.9,
                    model_provider="scripted",
                    model_name="ingest-quality-harness",
                ),
                WikiDraftBatchItem(
                    operation_index=1,
                    write_action="create",
                    title=topic["title"],
                    page_dir=topic["page_dir"],
                    question=topic["question"],
                    answer=topic["answer"],
                    summary=topic["summary"],
                    claims=topic["claims"],
                    entities=topic["entities"],
                    relations=topic["relations"],
                    evidence=[f"{claim_id} | {source_digest_id} | segment:{segment_title} | segment evidence supports {claim_id} | high" for claim_id in topic["claim_ids"]],
                    synthesis=topic["synthesis"],
                    key_points=topic["key_points"],
                    tags=topic["tags"],
                    source_digest_ids=[source_digest_id],
                    atom_ids=[atom_id],
                    confidence=0.88,
                    model_provider="scripted",
                    model_name="ingest-quality-harness",
                ),
            ],
            batch_summary="Compiled source digest and one stable knowledge object.",
            warnings=[],
        )

    def review_drafts(
        self,
        knowledge_extract: KnowledgeExtract,
        wiki_page_plan: WikiPagePlan,
        wiki_draft_batch: WikiDraftBatch,
        **_: object,
    ) -> IngestDraftReview:
        decisions: list[IngestDraftReviewDecision] = []
        for operation_index, risk in [(0, "low"), (1, "low")]:
            decisions.append(
                IngestDraftReviewDecision(
                    operation_index=operation_index,
                    decision="approve",
                    quality_score=0.9,
                    risk_level=risk,
                    write_safety="safe_create",
                    reason="The draft is directly supported by this segment and has a stable page boundary.",
                    required_changes=[],
                    dimension_scores=IngestReviewDimensionScores(
                        source_trace=0.9,
                        atom_coverage=0.9,
                        source_support=0.92,
                        page_boundary=0.9,
                        identity_fit=0.9,
                        duplication_risk=0.85,
                        relation_quality=0.88,
                        synthesis_quality=0.86,
                        maintainability=0.9,
                        update_safety=0.95,
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
            )
        return IngestDraftReview(decisions=decisions, batch_decision="approve", summary="Approved segmented source drafts.", warnings=[])


def _segment_metadata(document: SourceDocument) -> dict[str, object]:
    value = document.metadata.get("segmentation")
    return dict(value) if isinstance(value, dict) else {}


def _knowledge_source_type(document: SourceDocument) -> str:
    if document.origin.connector in {"codex", "hermes", "openclaw", "claude_code"} or document.source_type.endswith("_chat"):
        return "chat"
    if document.source_type == "markdown":
        return "markdown"
    return "document"


def _source_label(knowledge_extract: KnowledgeExtract) -> str:
    if knowledge_extract.source.source_app == "codex":
        return "Codex Golden Session"
    return "Long Agent Loop Note"


def _topic_for_extract(knowledge_extract: KnowledgeExtract) -> dict[str, object]:
    title = (knowledge_extract.source.title or "").lower()
    is_chat = knowledge_extract.source.source_app == "codex"
    if "workflow" in title or "2-3" in title:
        return {
            "page_dir": "workflows",
            "title": "Workflow Boundary Design",
            "knowledge_object": "workflow boundary design",
            "decision_reason": "Workflow boundaries are a reusable process design object.",
            "question": "How should workflow boundaries be designed?",
            "answer": "Workflow boundaries make deterministic execution explicit before semantic steps are invoked.",
            "summary": "Workflow boundaries separate deterministic orchestration from model-driven reasoning.",
            "claims": [
                "C1: Workflow boundaries make deterministic execution explicit before semantic steps are invoked.",
                "C2: Workflow boundaries separate orchestration from model-driven reasoning.",
            ],
            "claim_ids": ["C1", "C2"],
            "entities": ["[[Workflow Boundary Design]]", "[[Deterministic Execution]]", "[[Semantic Step]]"],
            "relations": [
                "[[Workflow Boundary Design]] | clarifies | [[Deterministic Execution]] | C1",
                "[[Workflow Boundary Design]] | separates | [[Semantic Step]] | C2",
            ],
            "synthesis": "Workflow boundary design keeps deterministic orchestration explicit while leaving semantic decisions inside reviewed contracts.",
            "key_points": ["Use workflows for predictable execution.", "Keep semantic decisions inside explicit contracts."],
            "tags": ["workflow", "architecture", "boundaries"],
        }
    if "harness" in title or "4-5" in title:
        return {
            "page_dir": "concepts",
            "title": "Golden Harness Evaluation",
            "knowledge_object": "golden harness evaluation",
            "decision_reason": "Golden harnesses are a reusable evaluation method.",
            "question": "What does a golden harness evaluate?",
            "answer": "A golden harness locks expected behavior for prompts, schemas, reports, and pipeline outputs.",
            "summary": "Golden harness evaluation makes semantic workflow changes reviewable without live model calls.",
            "claims": [
                "C1: Golden harness evaluation locks expected behavior for prompts, schemas, reports, and pipeline outputs.",
                "C2: Golden harness evaluation makes semantic workflow changes reviewable without live model calls.",
            ],
            "claim_ids": ["C1", "C2"],
            "entities": ["[[Golden Harness Evaluation]]", "[[Prompt Contract]]", "[[Pipeline Output]]"],
            "relations": [
                "[[Golden Harness Evaluation]] | validates | [[Prompt Contract]] | C1",
                "[[Golden Harness Evaluation]] | stabilizes | [[Pipeline Output]] | C2",
            ],
            "synthesis": "Golden harness evaluation provides deterministic review coverage for semantic workflow changes without requiring live model calls.",
            "key_points": ["Snapshot stable outputs.", "Use scripted semantic workflows for deterministic review."],
            "tags": ["testing", "harness", "evaluation"],
        }
    return {
        "page_dir": "queries" if is_chat else "concepts",
        "title": "Agent Loop Control Pattern" if not is_chat else "Agent Loop In KnoArbor",
        "knowledge_object": "agent loop control pattern",
        "decision_reason": "Agent loop control is the durable object in this segment.",
        "question": "What is the agent loop control pattern?",
        "answer": "An agent loop coordinates observation, reasoning, action, and feedback under explicit control boundaries.",
        "summary": "Agent loop control describes how an AI system repeatedly reasons, acts, observes results, and stops.",
        "claims": [
            "C1: Agent loop control coordinates observation, reasoning, action, and feedback.",
            "C2: Agent loop control requires explicit boundaries to stay auditable.",
        ],
        "claim_ids": ["C1", "C2"],
        "entities": ["[[Agent Loop Control Pattern]]", "[[Observation]]", "[[Tool Action]]", "[[Control Boundary]]"],
        "relations": [
            "[[Agent Loop Control Pattern]] | coordinates | [[Tool Action]] | C1",
            "[[Agent Loop Control Pattern]] | depends_on | [[Control Boundary]] | C2",
        ],
        "synthesis": "Agent loop control should be treated as a bounded execution pattern that ties reasoning, action, observation, and stopping conditions together.",
        "key_points": ["Model decisions are looped through tool results.", "Control boundaries keep the loop auditable."],
        "tags": ["agent-loop", "control", "ai-system"],
    }
