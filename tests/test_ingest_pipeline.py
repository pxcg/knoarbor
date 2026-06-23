from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import ConnectorConfig, KnoArborConfig, VaultConfig
from knoarbor.core.schemas.ingest_review import (
    IngestDraftReview,
    IngestDraftReviewDecision,
    IngestReviewChecks,
    IngestReviewDimensionScores,
)
from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeFact,
    KnowledgeRelation,
)
from knoarbor.core.schemas.knowledge_extract import CompileContext, ContentUnit, KnowledgeExtract, KnowledgeSource
from knoarbor.core.schemas.sources import RawSource, SourceContent, SourceDocument, SourceFingerprint, SourceOrigin, SourceRef
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_write import WikiPatchInput
from knoarbor.core.schemas.wiki_page_plan import WikiCandidatePage, WikiPageOperation, WikiPagePlan
from knoarbor.connectors.registry import ConnectorRegistry
from knoarbor.document_processing.schemas import DocumentProcessingItem, DocumentProcessingResult
from knoarbor.pipelines.ingest import IngestPipeline
from knoarbor.pipelines.source import SourcePipeline
from knoarbor.runtime import RunMonitor, run_monitor_context
from knoarbor.storage.knowledge_atom_index import read_knowledge_atom_records
from knoarbor.storage.wiki_paths import content_root


class FakeIngestSemanticWorkflow:
    def __init__(self) -> None:
        self.calls = 0
        self.last_document = None
        self.last_existing_wiki_index = None
        self.last_wiki_context = None
        self.last_candidate_page_context = None
        self.last_review_draft_batch = None

    def normalize(self, document, **kwargs):
        self.calls += 1
        self.last_document = document
        return IngestSemanticWorkflowFixtures.result(document).knowledge_extract

    def extract_atoms(self, source_digest, **kwargs):
        return KnowledgeAtomBatch(source_digest_id=source_digest.digest_id)

    def plan_pages(self, knowledge_extract, **kwargs):
        self.last_existing_wiki_index = kwargs.get("existing_wiki_index")
        self.last_wiki_context = kwargs.get("wiki_context")
        result = IngestSemanticWorkflowFixtures.result_from_extract(knowledge_extract).wiki_page_plan
        candidates = (self.last_wiki_context or {}).get("candidates", [])
        if candidates:
            result.operations[0].candidate_pages = [
                WikiCandidatePage(
                    path=candidates[0]["path"],
                    title=candidates[0]["title"],
                    match_reason="Candidate supplied by ingest context provider.",
                )
            ]
        return result

    def compile_drafts(self, knowledge_extract, wiki_page_plan, **kwargs):
        self.last_candidate_page_context = kwargs.get("candidate_page_context")
        return IngestSemanticWorkflowFixtures.result_from_extract(knowledge_extract).wiki_draft_batch

    def review_drafts(self, knowledge_extract, wiki_page_plan, wiki_draft_batch, **kwargs):
        self.last_review_draft_batch = wiki_draft_batch
        return IngestSemanticWorkflowFixtures.result_from_extract(knowledge_extract).ingest_draft_review


class FakeDocumentProcessingPipeline:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.ran = False

    def run(self, config):
        self.ran = True
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text("# Parsed Document\n\nProcessed before markdown discovery.", encoding="utf-8")
        return DocumentProcessingResult(
            items=[
                DocumentProcessingItem(
                    adapter="mineru",
                    input_path="paper.pdf",
                    output_path=str(self.output_path),
                    status="processed",
                    reason="test processor",
                )
            ],
            stats={"item_count": 1, "processed_count": 1, "failed_count": 0, "skipped_count": 0},
        )


class FailingSemanticWorkflow(FakeIngestSemanticWorkflow):
    def normalize(self, document, **kwargs):
        if "a_bad.md" in document.origin.raw_path:
            raise RuntimeError("model failed")
        return super().normalize(document, **kwargs)


class InvalidDraftSemanticWorkflow(FakeIngestSemanticWorkflow):
    def compile_drafts(self, knowledge_extract, wiki_page_plan, **kwargs):
        batch = super().compile_drafts(knowledge_extract, wiki_page_plan, **kwargs)
        batch.drafts[0].evidence = []
        return batch


class UnsupportedAtomSemanticWorkflow(FakeIngestSemanticWorkflow):
    def extract_atoms(self, source_digest, **kwargs):
        return KnowledgeAtomBatch(
            source_digest_id=source_digest.digest_id,
            claims=[
                KnowledgeClaim(
                    id="claim_agent_loop_unsupported",
                    claim="Agent loop is supported by a missing fact.",
                    claim_type="definition",
                    supporting_fact_ids=["missing_fact"],
                )
            ],
        )


class MismatchedWriteActionSemanticWorkflow(FakeIngestSemanticWorkflow):
    def compile_drafts(self, knowledge_extract, wiki_page_plan, **kwargs):
        batch = super().compile_drafts(knowledge_extract, wiki_page_plan, **kwargs)
        batch.drafts[0] = batch.drafts[0].model_copy(
            update={
                "write_action": "update",
                "target_page": "concepts/Agent-Loop.md",
                "patches": [
                    WikiPatchInput(
                        operation="merge_list",
                        section="Key Points",
                        items=["Mismatched update point."],
                    )
                ],
            }
        )
        return batch


class MissingAtomTraceSemanticWorkflow(FakeIngestSemanticWorkflow):
    def plan_pages(self, knowledge_extract, **kwargs):
        plan = super().plan_pages(knowledge_extract, **kwargs)
        plan.operations[0].selected_fact_ids = ["fact_agent_loop_cycle"]
        plan.operations[0].source_digest_ids = ["sd_test_agent"]
        return plan


class AtomTraceSemanticWorkflow(FakeIngestSemanticWorkflow):
    def extract_atoms(self, source_digest, **kwargs):
        evidence = KnowledgeEvidenceSpan(
            source_digest_id=source_digest.digest_id,
            source_path=source_digest.source.source_path,
            source_unit_index=0,
            excerpt="Agent loop repeats observe and act.",
        )
        return KnowledgeAtomBatch(
            source_digest_id=source_digest.digest_id,
            facts=[
                KnowledgeFact(
                    id="fact_agent_loop_cycle",
                    statement="Agent loop repeats observe and act.",
                    evidence=[evidence],
                )
            ],
            claims=[
                KnowledgeClaim(
                    id="claim_agent_loop_control",
                    claim="Agent loop is a control pattern.",
                    claim_type="definition",
                    supporting_fact_ids=["fact_agent_loop_cycle"],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="rel_agent_loop_mentions_workflow",
                    subject=KnowledgeAtomObject(object_type="concept", name="Agent Loop"),
                    predicate="relates_to",
                    object=KnowledgeAtomObject(object_type="workflow", name="Workflow"),
                    source_fact_ids=["fact_agent_loop_cycle"],
                )
            ],
        )

    def plan_pages(self, knowledge_extract, **kwargs):
        plan = super().plan_pages(knowledge_extract, **kwargs)
        plan.operations[0].selected_fact_ids = ["fact_agent_loop_cycle"]
        plan.operations[0].selected_claim_ids = ["claim_agent_loop_control"]
        plan.operations[0].selected_relation_ids = ["rel_agent_loop_mentions_workflow"]
        plan.operations[0].source_digest_ids = [kwargs["knowledge_atom_batch"].source_digest_id]
        return plan

    def compile_drafts(self, knowledge_extract, wiki_page_plan, **kwargs):
        batch = super().compile_drafts(knowledge_extract, wiki_page_plan, **kwargs)
        batch.drafts[0].atom_ids = [
            "fact_agent_loop_cycle",
            "claim_agent_loop_control",
            "rel_agent_loop_mentions_workflow",
        ]
        batch.drafts[0].source_digest_ids = [kwargs["knowledge_atom_batch"].source_digest_id]
        return batch


def _approved_decision(operation_index: int, *, write_safety: str = "safe_create") -> IngestDraftReviewDecision:
    return IngestDraftReviewDecision(
        operation_index=operation_index,
        decision="approve",
        quality_score=0.9,
        risk_level="low",
        write_safety=write_safety,
        reason="Draft is supported.",
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


class SourceOnlySemanticWorkflow(FakeIngestSemanticWorkflow):
    def plan_pages(self, knowledge_extract, **kwargs):
        source_digest_id = kwargs["knowledge_atom_batch"].source_digest_id
        return WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action="create",
                    page_dir="sources",
                    title="Long Source Digest",
                    knowledge_object="Long source provenance",
                    source_digest_ids=[source_digest_id],
                    decision_reason="Create source digest.",
                )
            ],
            overall_summary="Create source digest.",
        )

    def compile_drafts(self, knowledge_extract, wiki_page_plan, **kwargs):
        return WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action="create",
                    title="Long Source Digest",
                    page_dir="sources",
                    question="Long source",
                    answer=f"Segment evidence: {knowledge_extract.compile_context.primary_content[:30]}",
                    summary="Long source digest.",
                    claims=["C1: Source segments describe long source provenance."],
                    entities=["[[Long Source]]"],
                    relations=["[[Long Source]] | has_digest | [[Long Source Digest]] | C1"],
                    evidence=["C1 | source-level | full-source | source digest aggregates segmented input | high"],
                    synthesis="The source digest aggregates segmented source provenance into one audit page.",
                    key_points=["Source provenance."],
                    tags=["source"],
                    source_digest_ids=[kwargs["knowledge_atom_batch"].source_digest_id],
                    model_provider="test",
                    model_name="fake",
                )
            ],
            batch_summary="One source draft.",
        )

    def review_drafts(self, knowledge_extract, wiki_page_plan, wiki_draft_batch, **kwargs):
        return IngestDraftReview(
            decisions=[_approved_decision(0)],
            batch_decision="approve",
            summary="Approved source digest.",
        )


class SourceAndConceptSemanticWorkflow(FakeIngestSemanticWorkflow):
    def plan_pages(self, knowledge_extract, **kwargs):
        source_digest_id = kwargs["knowledge_atom_batch"].source_digest_id
        return WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action="create",
                    page_dir="sources",
                    title="Agent Source Digest",
                    knowledge_object="Agent source provenance",
                    source_digest_ids=[source_digest_id],
                    decision_reason="Create source digest.",
                ),
                WikiPageOperation(
                    action="create",
                    page_dir="concepts",
                    title="Agent Loop Control",
                    knowledge_object="Agent loop control",
                    selected_claim_ids=["claim_agent_loop_control"],
                    source_digest_ids=[source_digest_id],
                    decision_reason="Create durable concept.",
                ),
            ],
            overall_summary="Create source and concept.",
        )

    def compile_drafts(self, knowledge_extract, wiki_page_plan, **kwargs):
        return WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action="create",
                    title="Agent Source Digest",
                    page_dir="sources",
                    question="Agent loop source",
                    answer="Source digest for agent loop control.",
                    summary="Source digest for agent loop control.",
                    claims=["C1: Source digest documents agent loop control."],
                    entities=["[[Agent Loop]]"],
                    relations=["[[Agent Source]] | mentions | [[Agent Loop]] | C1"],
                    evidence=["C1 | raw/source | source-level | source digest support | medium"],
                    synthesis="Source digest for agent loop control.",
                    key_points=["Source provenance."],
                    tags=["source", "agent"],
                    source_digest_ids=[kwargs["knowledge_atom_batch"].source_digest_id],
                    model_provider="test",
                    model_name="fake",
                ),
                WikiDraftBatchItem(
                    operation_index=1,
                    write_action="create",
                    title="Agent Loop Control",
                    page_dir="concepts",
                    question="Agent loop source",
                    answer="Agent loop control repeats observe, decide, act, and feedback.",
                    summary="Agent loop control is a repeated control pattern.",
                    claims=["C1: [[Agent Loop]] control repeats observe, decide, act, and feedback."],
                    entities=["[[Agent Loop]]"],
                    relations=["[[Agent Loop]] | repeats | [[Control Cycle]] | C1"],
                    evidence=["C1 | sd_test | unit:0 | source states the loop cycle | high"],
                    synthesis="Agent loop control repeats observe, decide, act, and feedback.",
                    key_points=["Observe, decide, act."],
                    tags=["agent", "loop"],
                    source_digest_ids=[kwargs["knowledge_atom_batch"].source_digest_id],
                    atom_ids=["claim_agent_loop_control"],
                    model_provider="test",
                    model_name="fake",
                ),
            ],
            batch_summary="Source plus concept.",
        )

    def review_drafts(self, knowledge_extract, wiki_page_plan, wiki_draft_batch, **kwargs):
        return IngestDraftReview(
            decisions=[_approved_decision(0), _approved_decision(1)],
            batch_decision="approve",
            summary="Approved source and concept.",
        )


class ScenarioSemanticWorkflow(FakeIngestSemanticWorkflow):
    def __init__(self, *, action: str, page_dir: str = "concepts", target_page: str | None = None) -> None:
        super().__init__()
        self.action = action
        self.page_dir = page_dir
        self.target_page = target_page

    def plan_pages(self, knowledge_extract, **kwargs):
        self.last_existing_wiki_index = kwargs.get("existing_wiki_index")
        self.last_wiki_context = kwargs.get("wiki_context")
        source_digest_id = kwargs["knowledge_atom_batch"].source_digest_id
        if self.action == "skip":
            return WikiPagePlan(
                operations=[
                    WikiPageOperation(
                        action="skip",
                        page_dir="queries",
                        title="Low Value Source",
                        knowledge_object="Low value operational note",
                        decision_reason="Source is too thin and operational for durable wiki storage.",
                    )
                ],
                overall_summary="Skip low value source.",
                warnings=["low_value_source:too_thin"],
            )
        return WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action=self.action,
                    target_page=self.target_page,
                    page_dir=self.page_dir,
                    title=f"{self.page_dir.title()} Page",
                    knowledge_object=f"{self.page_dir} object",
                    selected_claim_ids=[] if self.page_dir == "sources" else ["claim_scenario"],
                    source_digest_ids=[source_digest_id],
                    candidate_pages=[
                        WikiCandidatePage(path=self.target_page, title="Existing", match_reason="Scenario target.")
                    ]
                    if self.target_page
                    else [],
                    decision_reason=f"Scenario {self.action} operation.",
                )
            ],
            overall_summary=f"Scenario {self.action}.",
        )

    def compile_drafts(self, knowledge_extract, wiki_page_plan, **kwargs):
        self.last_candidate_page_context = kwargs.get("candidate_page_context")
        if self.action == "skip":
            raise AssertionError("skip page plan should not compile drafts")
        patches = []
        if self.action == "update":
            patches = [
                WikiPatchInput(
                    operation="merge_list",
                    section="Key Points",
                    items=[f"{self.action} adds a durable point."],
                )
            ]
        write_action = self.action if self.action in {"create", "update"} else "create"
        return WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action=write_action,
                    target_page=self.target_page,
                    title=f"{self.page_dir.title()} Page",
                    page_dir=self.page_dir,
                    question="Scenario question",
                    answer=f"Scenario answer for {self.page_dir}.",
                    summary=f"Scenario summary for {self.page_dir}.",
                    claims=[f"C1: [[{self.page_dir.title()} Page]] has durable scenario evidence."],
                    entities=[f"[[{self.page_dir.title()} Page]]"],
                    relations=[f"[[{self.page_dir.title()} Page]] | mentions | [[Scenario]] | C1"],
                    evidence=["C1 | sd_test | unit:0 | scenario source support | high"],
                    synthesis=f"Scenario answer for {self.page_dir}.",
                    key_points=[f"{self.page_dir} key point."],
                    tags=[self.page_dir],
                    source_digest_ids=[kwargs["knowledge_atom_batch"].source_digest_id],
                    atom_ids=[] if self.page_dir == "sources" else ["claim_scenario"],
                    patches=patches,
                    model_provider="test",
                    model_name="fake",
                )
            ],
            batch_summary="Scenario draft.",
        )

    def review_drafts(self, knowledge_extract, wiki_page_plan, wiki_draft_batch, **kwargs):
        self.last_review_draft_batch = wiki_draft_batch
        if self.action == "skip":
            raise AssertionError("skip page plan should not review drafts")
        return IngestDraftReview(
            decisions=[
                IngestDraftReviewDecision(
                    operation_index=0,
                    decision="approve",
                    quality_score=0.9,
                    risk_level="low" if self.action == "create" else "medium",
                    write_safety="safe_create" if self.action == "create" else "safe_update",
                    reason="Scenario draft is supported.",
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
            ],
            batch_decision="approve",
            summary="Approved scenario draft.",
        )


class PartiallyFailingConnector:
    name = "partial"
    version = "partial@1"

    def discover(self, config):
        return [
            SourceRef(source_id="partial:bad", connector=self.name, source_type="markdown", uri="partial://bad", display_name="bad.md"),
            SourceRef(source_id="partial:good", connector=self.name, source_type="markdown", uri="partial://good", display_name="good.md"),
        ]

    def fetch(self, ref, config):
        if ref.source_id.endswith("bad"):
            raise RuntimeError("fetch failed")
        raw_path = str(Path(config.settings["raw_path"]).resolve())
        return RawSource(
            source_id=ref.source_id,
            raw_path=raw_path,
            content_hash="goodhash",
            content_type="text/markdown",
            bytes=12,
        )

    def to_document(self, raw, config):
        return SourceDocument(
            source_id=raw.source_id,
            source_type="markdown",
            origin=SourceOrigin(connector=self.name, uri="partial://good", raw_path=raw.raw_path),
            content=SourceContent(format="markdown", text="# Good\n\nContent"),
            metadata={"title": "Good"},
            fingerprint=SourceFingerprint(content_hash=raw.content_hash, connector_version=self.version),
        )


class IngestSemanticWorkflowFixtures:
    @staticmethod
    def result(document) -> object:
        return IngestSemanticWorkflowFixtures.result_from_extract(
            KnowledgeExtract(
                source=KnowledgeSource(
                    source_type="markdown",
                    source_app="markdown",
                    source_id=document.source_id,
                    source_path=document.origin.raw_path,
                    title=document.metadata.get("title") or "Note",
                ),
                content_units=[
                    ContentUnit(index=0, unit_type="note", role="note", content=document.content.text),
                ],
                compile_context=CompileContext(primary_content=document.content.text),
            )
        )

    @staticmethod
    def result_from_extract(knowledge_extract) -> object:
        return __import__("knoarbor.semantic.ingest_workflow", fromlist=["IngestSemanticWorkflowResult"]).IngestSemanticWorkflowResult(
            knowledge_extract=knowledge_extract,
            knowledge_atom_batch=KnowledgeAtomBatch(source_digest_id="test-digest"),
            wiki_page_plan=WikiPagePlan(
                operations=[
                    WikiPageOperation(
                        action="create",
                        page_dir="concepts",
                        title="Agent Loop",
                        knowledge_object="Agent Loop",
                        selected_claim_ids=["claim_agent_loop"],
                        source_digest_ids=["test-digest"],
                        decision_reason="Useful concept page.",
                    )
                ],
                overall_summary="Create one concept page.",
            ),
            wiki_draft_batch=WikiDraftBatch(
                drafts=[
                    WikiDraftBatchItem(
                        operation_index=0,
                        write_action="create",
                        title="Agent Loop",
                        page_dir="concepts",
                        question="Agent Loop",
                        answer="Agent loop repeats observe, decide, act, and feedback.",
                        summary="Agent loop is a control pattern.",
                        claims=["C1: [[Agent Loop]] repeats observe, decide, act, and feedback."],
                        entities=["[[Agent Loop]]"],
                        relations=["[[Agent Loop]] | repeats | [[Control Cycle]] | C1"],
                        evidence=["C1 | test-digest | unit:0 | source states the loop cycle | high"],
                        synthesis="Agent loop repeats observe, decide, act, and feedback.",
                        key_points=["Observe, decide, act."],
                        tags=["agent", "loop"],
                        source_digest_ids=["test-digest"],
                        atom_ids=["claim_agent_loop"],
                        model_provider="test",
                        model_name="fake",
                    )
                ],
                batch_summary="One draft.",
            ),
            ingest_draft_review=IngestDraftReview(
                decisions=[
                    IngestDraftReviewDecision(
                        operation_index=0,
                        decision="approve",
                        quality_score=0.9,
                        risk_level="low",
                        write_safety="safe_create",
                        reason="Draft is supported.",
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
                ],
                batch_decision="approve",
                summary="Approved.",
            ),
        )


class IngestPipelineTests(unittest.TestCase):
    def test_connector_ingest_writes_and_then_skips_unchanged_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "agent.md").write_text(
                "# Agent Loop\n\nObserve and act.\n\nContact alice@example.com\nDEEPSEEK_API_KEY=sk-abcdefghijklmnop1234567890",
                encoding="utf-8",
            )
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            semantic = FakeIngestSemanticWorkflow()
            pipeline = IngestPipeline(semantic)  # type: ignore[arg-type]

            first = pipeline.run(config, connector_names=["markdown"], write=True)
            second = pipeline.run(config, connector_names=["markdown"], write=True)

        self.assertEqual(first.stats["processed_count"], 1)
        self.assertEqual(first.stats["written_count"], 1)
        self.assertEqual(second.stats["processed_count"], 0)
        self.assertEqual(second.stats["skipped_count"], 1)
        self.assertEqual(semantic.calls, 1)
        self.assertIsNotNone(semantic.last_document)
        self.assertNotIn("alice@example.com", semantic.last_document.content.text)
        self.assertNotIn("sk-abcdefghijklmnop1234567890", semantic.last_document.content.text)
        self.assertGreater(first.results[0].redaction["redacted_count"], 0)
        self.assertIsNotNone(semantic.last_review_draft_batch)
        self.assertEqual(semantic.last_review_draft_batch.drafts[0].source_file, str((notes / "agent.md").resolve()))
        self.assertTrue((first.report_path or "").startswith("maintenance/ingest_report_"))
        self.assertEqual(first.ledger_path, "maintenance/ingest_ledger.jsonl")

    def test_long_markdown_source_is_segmented_before_semantic_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "long.md").write_text(
                "# Part One\n\n" + "a" * 9000 + "\n\n## Part Two\n\n" + "b" * 9000 + "\n\n## Part Three\n\n" + "c" * 9000,
                encoding="utf-8",
            )
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            semantic = FakeIngestSemanticWorkflow()
            pipeline = IngestPipeline(semantic)  # type: ignore[arg-type]

            result = pipeline.run(config, connector_names=["markdown"], write=False)

        source = result.results[0]
        self.assertEqual(source.segmentation["mode"], "heading")
        self.assertEqual(source.segmentation["segment_count"], 3)
        self.assertEqual(len(source.segments), 3)
        self.assertEqual(semantic.calls, 3)
        self.assertEqual(result.stats["processed_count"], 1)

    def test_segmented_ingest_merges_duplicate_source_digests_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "long.md").write_text(
                "# Part One\n\n" + "a" * 9000 + "\n\n## Part Two\n\n" + "b" * 9000 + "\n\n## Part Three\n\n" + "c" * 9000,
                encoding="utf-8",
            )
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            pipeline = IngestPipeline(SourceOnlySemanticWorkflow())  # type: ignore[arg-type]

            result = pipeline.run(config, connector_names=["markdown"], write=True, write_report=False, append_ledger=False)
            source = result.results[0]
            source_pages = sorted((content_root(vault) / "sources").glob("*.md"))
            self.assertEqual(len(source_pages), 1)
            self.assertEqual(result.stats["written_count"], 1)
            self.assertEqual(source.generated_pages, ["sources/Long-Source-Digest.md"])
            self.assertEqual(source.context["write_policy"]["changes"], ["merged_source_digest_creates:3->1"])

    def test_ingest_uses_provenance_links_without_broad_lexical_related_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Existing-Agent.md").write_text(
                "# Existing Agent\n\nAgent loop source matching text should not be linked by lexical scan.",
                encoding="utf-8",
            )
            (notes / "agent.md").write_text("# Agent Loop\n\nObserve and act.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            pipeline = IngestPipeline(SourceAndConceptSemanticWorkflow())  # type: ignore[arg-type]

            result = pipeline.run(config, connector_names=["markdown"], write=True, write_report=False, append_ledger=False)
            self.assertEqual(result.stats["written_count"], 2)
            source_page = (vault / "sources" / "Agent-Source-Digest.md").read_text(encoding="utf-8")
            concept_page = (vault / "Agent-Loop-Control.md").read_text(encoding="utf-8")
            self.assertNotIn("## Related Pages", source_page)
            self.assertNotIn("## Related Pages", concept_page)
            self.assertIn("## Evidence", source_page)
            self.assertIn("## Evidence", concept_page)
            self.assertNotIn("Existing-Agent", source_page)
            self.assertNotIn("Existing-Agent", concept_page)

    def test_document_processing_runs_before_markdown_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            processed = root / "raw" / "documents" / "markdown" / "paper.md"
            vault.mkdir(parents=True)
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(processed.parent)]},
                    )
                },
            )
            processor = FakeDocumentProcessingPipeline(processed)
            pipeline = IngestPipeline(  # type: ignore[arg-type]
                FakeIngestSemanticWorkflow(),
                document_processing_pipeline=processor,
            )

            result = pipeline.run(config, connector_names=["markdown"], write=False)

        self.assertTrue(processor.ran)
        self.assertEqual(result.document_processing.stats["processed_count"], 1)
        self.assertEqual(result.stats["document_processing_count"], 1)
        self.assertEqual(result.stats["processed_count"], 1)
        self.assertEqual(result.results[0].source_file, str(processed.resolve()))

    def test_prepared_file_ingest_keeps_document_processing_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            source = root / "parsed.md"
            vault.mkdir(parents=True)
            source.write_text("# Parsed File\n\nContent.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(source)], "pattern": source.name, "recursive": False},
                    )
                },
            )
            processing = DocumentProcessingResult(
                items=[
                    DocumentProcessingItem(
                        adapter="mineru",
                        input_path=str(root / "paper.pdf"),
                        output_path=str(source),
                        status="processed",
                        reason="test processor",
                    )
                ],
                stats={"item_count": 1, "processed_count": 1, "failed_count": 0, "skipped_count": 0},
            )
            pipeline = IngestPipeline(FakeIngestSemanticWorkflow())  # type: ignore[arg-type]

            result = pipeline.run(
                config,
                connector_names=["markdown"],
                write=False,
                write_report=False,
                append_ledger=False,
                document_processing_result=processing,
            )

        self.assertEqual(result.document_processing.stats["processed_count"], 1)
        self.assertEqual(result.stats["document_processing_count"], 1)
        self.assertEqual(result.results[0].source_file, str(source.resolve()))

    def test_ingest_builds_single_candidate_pool_and_materializes_selected_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            (vault / "concepts").mkdir(parents=True)
            notes.mkdir()
            (vault / "concepts" / "Agent-Control-Patterns.md").write_text(
                "\n".join(
                    [
                        "# Agent Control Patterns",
                        "",
                        "---",
                        "type: concept",
                        "status: draft",
                        "---",
                        "",
                        "## Summary",
                        "Agent loop control patterns coordinate observe, decide, act, and feedback.",
                        "",
                        "## Key Points",
                        "- Agent loop is a repeated control cycle.",
                    ]
                ),
                encoding="utf-8",
            )
            (notes / "agent.md").write_text("# Agent Loop\n\nAgent loop control patterns.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            semantic = FakeIngestSemanticWorkflow()
            pipeline = IngestPipeline(semantic)  # type: ignore[arg-type]

            result = pipeline.run(config, connector_names=["markdown"], write=False)

        self.assertEqual(result.stats["processed_count"], 1)
        self.assertIsNotNone(semantic.last_wiki_context)
        self.assertGreater(semantic.last_existing_wiki_index["content_length"], 0)
        self.assertEqual(semantic.last_existing_wiki_index["path"], ".knoarbor/index/manifest.json")
        self.assertIn("candidate", semantic.last_existing_wiki_index["note"])
        self.assertGreaterEqual(len(semantic.last_wiki_context["candidates"]), 1)
        self.assertEqual(semantic.last_wiki_context["candidates"][0]["path"], "concepts/Agent-Control-Patterns.md")
        self.assertIsNotNone(semantic.last_candidate_page_context)
        self.assertEqual(result.results[0].context["retrieval"]["candidate_count"], 1)

    def test_ingest_context_reranks_same_source_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            (vault / "concepts").mkdir(parents=True)
            notes.mkdir()
            (vault / "concepts" / "General-Agent-Loop.md").write_text(
                "\n".join(
                    [
                        "# General Agent Loop",
                        "",
                        "---",
                        "type: concept",
                        "status: draft",
                        "source: raw/notes/other.md",
                        "---",
                        "",
                        "## Summary",
                        "Agent loop control patterns coordinate observe, decide, act, and feedback in detail.",
                    ]
                ),
                encoding="utf-8",
            )
            note_path = notes / "agent.md"
            (vault / "concepts" / "Specific-Agent-Loop.md").write_text(
                "\n".join(
                    [
                        "# Specific Agent Loop",
                        "",
                        "---",
                        "type: concept",
                        "status: draft",
                        f"source: {note_path}",
                        "---",
                        "",
                        "## Summary",
                        "Agent loop.",
                    ]
                ),
                encoding="utf-8",
            )
            note_path.write_text("# Agent Loop\n\nAgent loop.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            semantic = FakeIngestSemanticWorkflow()
            pipeline = IngestPipeline(semantic)  # type: ignore[arg-type]

            pipeline.run(config, connector_names=["markdown"], write=False)

        self.assertIsNotNone(semantic.last_wiki_context)
        self.assertEqual(semantic.last_wiki_context["candidates"][0]["path"], "concepts/Specific-Agent-Loop.md")
        self.assertIn("source_overlap", semantic.last_wiki_context["candidates"][0]["matched_fields"])

    def test_ingest_writes_compact_report_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "agent.md").write_text("# Agent Loop\n\nObserve and act.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            monitor = RunMonitor(vault_path=vault, flow="ingest", run_id="ingest-report-test")
            with run_monitor_context(monitor):
                result = IngestPipeline(FakeIngestSemanticWorkflow()).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]

            report_path = vault / (result.report_path or "")
            ledger_path = vault / (result.ledger_path or "")

            self.assertTrue(report_path.exists())
            self.assertTrue(ledger_path.exists())
            report = report_path.read_text(encoding="utf-8")
            ledger_record = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[-1])

        self.assertIn("# Ingest Report", report)
        self.assertEqual(result.report_path, "maintenance/ingest_report_ingest-report-test.md")
        self.assertEqual(ledger_record["run_id"], "ingest-report-test")
        self.assertIn("source_digest:", report)
        self.assertIn("evidence_spans=", report)
        self.assertIn("knowledge_atoms:", report)
        self.assertIn("unsupported=0", report)
        self.assertIn("conflicting=0", report)
        self.assertIn("rejected=0", report)
        self.assertIn("Page plan operations:", report)
        self.assertEqual(ledger_record["schema_version"], "ingest_run.v1")
        self.assertEqual(ledger_record["stats"]["processed_count"], 1)
        self.assertEqual(ledger_record["stats"]["segment_count"], 1)
        self.assertEqual(ledger_record["stats"]["failed_segment_count"], 0)
        self.assertEqual(ledger_record["sources"][0]["generated_pages"], ["Agent-Loop.md"])
        self.assertEqual(ledger_record["sources"][0]["scoped_lint"]["scope"], "latest_ingest_source")
        self.assertIn("Agent-Loop.md", ledger_record["sources"][0]["touched_pages"])
        self.assertTrue(ledger_record["sources"][0]["scoped_lint_result"]["deterministic_lint"]["stats"]["scoped"])
        self.assertIn("policy_decision", ledger_record["sources"][0]["scoped_lint_result"])
        self.assertIn("## Run Summary", report)
        self.assertIn("- segment_status: written=1", report)
        self.assertIn("scoped_lint_issues:", report)

    def test_ingest_writes_knowledge_atom_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "agent.md").write_text("# Agent Loop\n\nObserve and act.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )

            result = IngestPipeline(AtomTraceSemanticWorkflow()).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]
            records = read_knowledge_atom_records(vault)

        self.assertEqual(result.results[0].generated_pages, ["Agent-Loop.md"])
        self.assertEqual(result.results[0].context["knowledge_atom_index_path"], ".knoarbor/index/knowledge_atoms.jsonl")
        self.assertEqual(len(records), 3)
        fact = next(record for record in records if record.atom_id == "fact_agent_loop_cycle")
        self.assertEqual(fact.page_paths, ["Agent-Loop.md"])

    def test_ingest_report_includes_knowledge_atom_index_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "agent.md").write_text("# Agent Loop\n\nObserve and act.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            monitor = RunMonitor(vault_path=vault, flow="ingest", run_id="atom-index-report-test")
            with run_monitor_context(monitor):
                result = IngestPipeline(AtomTraceSemanticWorkflow()).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]

            report = (vault / (result.report_path or "")).read_text(encoding="utf-8")

        self.assertIn("- knowledge_atom_index: .knoarbor/index/knowledge_atoms.jsonl", report)
        self.assertIn("Draft atom traces:", report)
        self.assertIn("fact_agent_loop_cycle", report)

    def test_ingest_records_source_failure_and_continues_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "a_bad.md").write_text("# Bad\n\nThis source fails.", encoding="utf-8")
            (notes / "b_good.md").write_text("# Good\n\nThis source succeeds.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )

            result = IngestPipeline(FailingSemanticWorkflow()).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]
            failed = [item for item in result.results if item.status == "failed"]
            written = [item for item in result.results if item.status == "written"]
            report = (vault / (result.report_path or "")).read_text(encoding="utf-8")

        self.assertEqual(result.stats["failed_count"], 1)
        self.assertEqual(result.stats["written_count"], 1)
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(written), 1)
        self.assertEqual(failed[0].error_stage, "source")
        self.assertEqual(failed[0].error_code, "KA-INTERNAL-001")
        self.assertEqual(failed[0].error_type, "RuntimeError")
        self.assertIn("model failed", failed[0].error_message or "")
        self.assertIn("- failed: 1", report)
        self.assertIn("failure_summary:", report)
        self.assertIn("error_code: KA-INTERNAL-001", report)
        self.assertIn("error_type: RuntimeError", report)

    def test_quality_gate_blocks_invalid_approved_draft_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "agent.md").write_text("# Agent Loop\n\nObserve and act.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )

            result = IngestPipeline(InvalidDraftSemanticWorkflow()).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]
            source = result.results[0]
            report = (vault / (result.report_path or "")).read_text(encoding="utf-8")

        self.assertEqual(source.status, "failed")
        self.assertEqual(source.error_stage, "quality_gate")
        self.assertEqual(source.error_code, "KA-INPUT-001")
        self.assertIn("missing_evidence", source.error_message or "")
        self.assertEqual(source.generated_pages, [])
        self.assertFalse((vault / "concepts" / "Agent-Loop.md").exists())
        self.assertIn("quality_gate_passed: False", report)

    def test_quality_gate_blocks_atom_quality_errors_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "agent.md").write_text("# Agent Loop\n\nObserve and act.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )

            result = IngestPipeline(UnsupportedAtomSemanticWorkflow()).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]
            source = result.results[0]
            report = (vault / (result.report_path or "")).read_text(encoding="utf-8")

        self.assertEqual(source.status, "failed")
        self.assertEqual(source.error_stage, "quality_gate")
        self.assertEqual(source.error_code, "KA-INPUT-001")
        self.assertIn("knowledge_atom_unsupported_claim", source.error_message or "")
        self.assertEqual(source.generated_pages, [])
        self.assertIn("quality_gate_passed: False", report)

    def test_quality_gate_blocks_write_action_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "agent.md").write_text("# Agent\n\nAgent loop.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )

            result = IngestPipeline(MismatchedWriteActionSemanticWorkflow()).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]
            source = result.results[0]

        self.assertEqual(source.status, "failed")
        self.assertEqual(source.error_stage, "quality_gate")
        self.assertEqual(source.error_code, "KA-INPUT-001")
        self.assertIn("write_action_mismatch", source.error_message or "")
        self.assertEqual(source.generated_pages, [])

    def test_quality_gate_blocks_missing_atom_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "agent.md").write_text("# Agent\n\nAgent loop.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )

            result = IngestPipeline(MissingAtomTraceSemanticWorkflow()).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]
            source = result.results[0]

        self.assertEqual(source.status, "failed")
        self.assertEqual(source.error_stage, "quality_gate")
        self.assertEqual(source.error_code, "KA-INPUT-001")
        self.assertIn("missing_selected_atom_trace", source.error_message or "")
        self.assertIn("missing_source_digest_trace", source.error_message or "")

    def test_relation_update_operation_patches_existing_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            (vault / "concepts").mkdir(parents=True)
            notes.mkdir()
            (vault / "concepts" / "Existing.md").write_text(
                "\n".join(
                    [
                        "# Existing",
                        "",
                        "---",
                        "type: concept",
                        "status: draft",
                        "---",
                        "",
                        "## Summary",
                        "Existing summary.",
                        "",
                        "## Answer",
                        "Existing answer.",
                        "",
                        "## Key Points",
                        "- Existing point.",
                        "",
                        "## Related Pages",
                        "- 暂无关联知识",
                        "",
                        "## Tags",
                        "- existing",
                        "",
                        "## Source",
                        "raw/notes/existing.md",
                    ]
                ),
                encoding="utf-8",
            )
            (notes / "update.md").write_text("# update\n\nPatch existing page.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            semantic = ScenarioSemanticWorkflow(action="update", target_page="concepts/Existing.md")

            result = IngestPipeline(semantic).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]
            content = (vault / "concepts" / "Existing.md").read_text(encoding="utf-8")

        self.assertEqual(result.stats["written_count"], 1)
        self.assertIn("update adds a durable point.", content)
        self.assertEqual(result.results[0].generated_pages, ["concepts/Existing.md"])

    def test_relation_skip_records_semantic_skip_reason_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            (notes / "thin.md").write_text("todo", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )

            result = IngestPipeline(ScenarioSemanticWorkflow(action="skip")).run(config, connector_names=["markdown"], write=True)  # type: ignore[arg-type]
            report = (vault / (result.report_path or "")).read_text(encoding="utf-8")
            checkpoint_state = json.loads((vault / "maintenance" / "source_ingest_checkpoints.json").read_text(encoding="utf-8"))

        self.assertEqual(result.results[0].status, "skipped")
        self.assertEqual(result.stats["skipped_count"], 1)
        self.assertIn("too thin", result.results[0].semantic_skip_reason or "")
        self.assertEqual(result.results[0].generated_pages, [])
        self.assertIn("semantic_skip_reason:", report)
        self.assertEqual(len(checkpoint_state["sources"]), 1)

    def test_timeline_and_workflow_page_dirs_write_expected_types(self) -> None:
        for page_dir, page_type in [("timelines", "timeline"), ("workflows", "workflow")]:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                vault = root / "vaults" / "all"
                notes = root / "notes"
                vault.mkdir(parents=True)
                notes.mkdir()
                (notes / f"{page_dir}.md").write_text(f"# {page_dir}\n\nDurable {page_dir}.", encoding="utf-8")
                config = KnoArborConfig(
                    vault=VaultConfig(path=vault),
                    connectors={
                        "markdown": ConnectorConfig(
                            enabled=True,
                            settings={"roots": [str(notes)]},
                        )
                    },
                )

                result = IngestPipeline(ScenarioSemanticWorkflow(action="create", page_dir=page_dir)).run(  # type: ignore[arg-type]
                    config,
                    connector_names=["markdown"],
                    write=True,
                )
                page = content_root(vault) / result.results[0].generated_pages[0]
                content = page.read_text(encoding="utf-8")

            self.assertNotIn("type: page", content)
            self.assertNotIn(f"page_kind: {page_type}", content)
            self.assertFalse(result.results[0].generated_pages[0].startswith(f"{page_dir}/"))

    def test_hermes_connector_uses_incremental_session_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            sessions = root / "sessions"
            vault.mkdir(parents=True)
            sessions.mkdir()
            session_path = sessions / "session_demo.json"
            session_path.write_text(
                json.dumps(
                    {
                        "session_id": "demo",
                        "platform": "cli",
                        "messages": [
                            {"role": "user", "content": "first"},
                            {"role": "assistant", "content": "answer"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "hermes": ConnectorConfig(
                        enabled=True,
                        settings={"sessions_dir": str(sessions)},
                    )
                },
            )
            semantic = FakeIngestSemanticWorkflow()
            pipeline = IngestPipeline(semantic)  # type: ignore[arg-type]

            first = pipeline.run(config, connector_names=["hermes"], write=True)
            session_path.write_text(
                json.dumps(
                    {
                        "session_id": "demo",
                        "platform": "cli",
                        "messages": [
                            {"role": "user", "content": "first"},
                            {"role": "assistant", "content": "answer"},
                            {"role": "user", "content": "second"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            second = pipeline.run(config, connector_names=["hermes"], write=True)
            processed_payload = json.loads(semantic.last_document.content.text)
            third = pipeline.run(config, connector_names=["hermes"], write=True)

        self.assertEqual(first.results[0].checkpoint["checkpoint_type"], "session")
        self.assertEqual(first.results[0].mode, "new_session")
        self.assertEqual(second.results[0].mode, "incremental")
        self.assertEqual(processed_payload["messages"], [{"role": "user", "content": "second"}])
        self.assertEqual(semantic.last_document.checkpoint.mode, "incremental")
        self.assertEqual(semantic.last_document.checkpoint.from_index, 2)
        self.assertEqual(third.results[0].status, "skipped")

    def test_source_pipeline_item_failure_does_not_abort_connector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            raw = root / "good.md"
            vault.mkdir(parents=True)
            raw.write_text("# Good\n\nContent", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "partial": ConnectorConfig(
                        enabled=True,
                        settings={"raw_path": str(raw)},
                    )
                },
            )
            source_pipeline = SourcePipeline(ConnectorRegistry([PartiallyFailingConnector()]))  # type: ignore[list-item]
            result = IngestPipeline(FakeIngestSemanticWorkflow(), source_pipeline=source_pipeline).run(  # type: ignore[arg-type]
                config,
                connector_names=["partial"],
                write=True,
            )

        self.assertEqual(result.stats["source_count"], 2)
        self.assertEqual(result.stats["failed_count"], 1)
        self.assertEqual(result.stats["written_count"], 1)
        self.assertEqual(result.results[0].status, "failed")
        self.assertEqual(result.results[0].error_stage, "fetch")
        self.assertEqual(result.results[0].error_code, "KA-INTERNAL-001")
        self.assertEqual(result.results[1].status, "written")

    def test_missing_source_checkpoint_creates_lifecycle_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            source_path = notes / "agent.md"
            source_path.write_text("# Agent Loop\n\nObserve and act.", encoding="utf-8")
            config = KnoArborConfig(
                vault=VaultConfig(path=vault),
                connectors={
                    "markdown": ConnectorConfig(
                        enabled=True,
                        settings={"roots": [str(notes)]},
                    )
                },
            )
            pipeline = IngestPipeline(FakeIngestSemanticWorkflow())  # type: ignore[arg-type]

            first = pipeline.run(config, connector_names=["markdown"], write=True)
            source_path.unlink()
            second = pipeline.run(config, connector_names=["markdown"], write=True)
            report = (vault / (second.report_path or "")).read_text(encoding="utf-8")

        self.assertEqual(first.stats["written_count"], 1)
        self.assertEqual(second.stats["lifecycle_candidate_count"], 1)
        self.assertEqual(second.lifecycle_candidates[0].issue_type, "source_missing")
        self.assertEqual(second.lifecycle_candidates[0].target_page, "Agent-Loop.md")
        self.assertIn("Source Lifecycle Candidates", report)
        self.assertIn("source_missing", report)


if __name__ == "__main__":
    unittest.main()
