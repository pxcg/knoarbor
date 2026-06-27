from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.ingest_review import IngestDraftReview
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan
from knoarbor.semantic import build_source_normalize_input, load_semantic_contract


class SemanticContractTests(unittest.TestCase):
    def test_ingest_semantic_contracts_load_prompt_and_schema(self) -> None:
        expected = {
            "source_normalize": ("knowledge_extract.v1", KnowledgeExtract),
            "wiki_atom_extract": ("knowledge_atoms.v2", KnowledgeAtomBatch),
            "wiki_page_plan": ("wiki_page_plan.v1", WikiPagePlan),
            "wiki_draft_compile": ("wiki_draft_batch.v1", WikiDraftBatch),
            "ingest_draft_review": ("ingest_draft_review.v2", IngestDraftReview),
            "lint_diagnose": ("maintenance_candidates.v1", MaintenanceCandidates),
            "lint_quality_diagnose": ("maintenance_candidates.v1", MaintenanceCandidates),
            "lint_maintenance_review": ("lint_maintenance_review.v1", LintMaintenanceReview),
            "lint_draft_compile": ("wiki_draft_batch.v1", WikiDraftBatch),
        }

        for contract_name, (schema_version, schema_model) in expected.items():
            with self.subTest(contract_name=contract_name):
                contract = load_semantic_contract(contract_name)

                self.assertEqual(contract.schema_version, schema_version)
                self.assertIs(contract.schema_model, schema_model)
                self.assertIn(schema_version, contract.prompt_text)

        self.assertIn("source_document.v1", load_semantic_contract("source_normalize").prompt_text)

    def test_knowledge_extract_schema_accepts_current_agent_output_shape(self) -> None:
        extract = KnowledgeExtract.model_validate(
            {
                "schema_version": "knowledge_extract.v1",
                "source": {
                    "source_type": "markdown",
                    "source_app": "personal_vault",
                    "source_id": "markdown:abc",
                    "source_path": "raw/inbox/notes/Agent.md",
                    "title": "Agent",
                    "created_at": None,
                    "updated_at": None,
                },
                "content_units": [
                    {
                        "index": 0,
                        "unit_type": "section",
                        "role": "note",
                        "title": "Agent Loop",
                        "content": "Agent loop notes.",
                        "timestamp": None,
                        "is_primary": True,
                        "metadata": {"heading_level": 1},
                    }
                ],
                "compile_context": {
                    "primary_content": "# Agent\n\nAgent loop notes.",
                    "supporting_evidence": [],
                    "links": [],
                    "latest_unit_indexes": [0],
                },
                "confidence": 0.9,
                "warnings": [],
            }
        )

        self.assertEqual(extract.source.title, "Agent")
        self.assertEqual(extract.content_units[0].role, "note")
        self.assertEqual(extract.compile_context.latest_unit_indexes, [0])

    def test_knowledge_extract_normalizes_link_objects(self) -> None:
        extract = KnowledgeExtract.model_validate(
            {
                "schema_version": "knowledge_extract.v1",
                "source": {
                    "source_type": "markdown",
                    "source_app": "markdown",
                    "title": "LLM Wiki",
                },
                "compile_context": {
                    "links": [
                        {"url": "https://example.com/wiki", "title": "Example"},
                        {"title": "Fallback title"},
                        "raw/inbox/notes/LLM-Wiki.md",
                    ]
                },
            }
        )

        self.assertEqual(
            extract.compile_context.links,
            ["https://example.com/wiki", "Fallback title", "raw/inbox/notes/LLM-Wiki.md"],
        )

    def test_source_document_builds_stable_normalize_input(self) -> None:
        document = SourceDocument(
            source_id="markdown:abc",
            source_type="markdown",
            origin=SourceOrigin(
                connector="markdown",
                uri="file:///tmp/Agent.md",
                raw_path="raw/inbox/notes/Agent.md",
            ),
            content=SourceContent(format="markdown", text="# Agent\n\nLoop notes."),
            metadata={"title": "Agent"},
            fingerprint=SourceFingerprint(content_hash="abc", connector_version="markdown@1"),
        )

        payload = build_source_normalize_input(document)

        self.assertEqual(payload["source_hint"]["source_type"], "markdown")
        self.assertEqual(payload["source_hint"]["source_app"], "markdown")
        self.assertEqual(payload["source_hint"]["source_path"], "raw/inbox/notes/Agent.md")
        self.assertEqual(payload["source_document"]["schema_version"], "source_document.v1")

    def test_wiki_page_plan_schema_accepts_actionable_operations(self) -> None:
        plan = WikiPagePlan.model_validate(
            {
                "operations": [
                    {
                        "action": "create",
                        "target_page": None,
                        "page_dir": "pages",
                        "canonical_path": "/Agent-Loop.md",
                        "title": "Agent Loop",
                        "knowledge_object": "Agent Loop control pattern",
                        "selected_claim_ids": ["claim_agent_loop_pattern"],
                        "selected_relation_ids": ["rel_agent_loop_mentions_control"],
                        "source_digest_ids": ["sd_agent_loop"],
                        "candidate_pages": [],
                        "entity_mappings": [
                            {
                                "source_name": "A2A",
                                "canonical_name": "Agent-to-Agent Protocol",
                                "aliases": ["A2A Protocol"],
                                "target_page": "pages/Agent-to-Agent-Protocol.md",
                                "atom_id": "entity_a2a",
                                "reason": "The candidate profile uses the expanded protocol name.",
                            }
                        ],
                        "relation_mappings": [
                            {
                                "relation_id": "rel_agent_loop_mentions_control",
                                "canonical_subject": "Agent Loop",
                                "predicate": "includes",
                                "canonical_object": "Agent Control",
                                "subject_page": "Agent-Loop.md",
                                "object_page": "Agent-Control.md",
                                "supporting_claim_ids": ["claim_agent_loop_pattern"],
                                "reason": "The selected claim supports the relation.",
                            }
                        ],
                        "cross_page_relations": [
                            {
                                "relation_id": "rel_agent_loop_mentions_control",
                                "target_page": "Agent-Control.md",
                                "direction": "outgoing",
                                "supporting_claim_ids": ["claim_agent_loop_pattern"],
                                "reason": "The relation connects the planned page to the control page.",
                            }
                        ],
                        "decision_reason": "The source contains a durable reusable concept.",
                    },
                    {
                        "action": "update",
                        "target_page": "OpenClaw.md",
                        "page_dir": "pages",
                        "title": "OpenClaw",
                        "knowledge_object": "OpenClaw engineering agent",
                        "selected_claim_ids": ["claim_openclaw_agent"],
                        "source_digest_ids": ["sd_agent_loop"],
                        "candidate_pages": [],
                        "decision_reason": "The existing page covers the same entity.",
                    },
                ],
                "overall_summary": "Create one concept page and update one related entity page.",
                "confidence": 0.86,
                "warnings": [],
            }
        )

        self.assertEqual(len(plan.operations), 2)
        self.assertEqual(plan.operations[0].canonical_path, "Agent-Loop.md")
        self.assertEqual(plan.operations[0].selected_claim_ids, ["claim_agent_loop_pattern"])
        self.assertEqual(plan.operations[0].source_digest_ids, ["sd_agent_loop"])
        self.assertEqual(plan.operations[0].entity_mappings[0].canonical_name, "Agent-to-Agent Protocol")
        self.assertEqual(plan.operations[0].relation_mappings[0].predicate, "includes")
        self.assertEqual(plan.operations[0].cross_page_relations[0].target_page, "Agent-Control.md")
        self.assertEqual(plan.operations[1].target_page, "OpenClaw.md")

    def test_wiki_page_plan_rejects_mapping_for_unselected_relation(self) -> None:
        with self.assertRaises(ValueError):
            WikiPagePlan.model_validate(
                {
                    "operations": [
                        {
                            "action": "create",
                            "target_page": None,
                            "page_dir": "pages",
                            "canonical_path": "Agent-Loop.md",
                            "title": "Agent Loop",
                            "knowledge_object": "Agent Loop",
                            "selected_claim_ids": ["claim_agent_loop_pattern"],
                            "selected_relation_ids": [],
                            "source_digest_ids": ["sd_agent_loop"],
                            "candidate_pages": [],
                            "relation_mappings": [
                                {
                                    "relation_id": "rel_agent_loop_mentions_control",
                                    "canonical_subject": "Agent Loop",
                                    "predicate": "includes",
                                    "canonical_object": "Agent Control",
                                    "supporting_claim_ids": ["claim_agent_loop_pattern"],
                                    "reason": "The relation was not selected.",
                                }
                            ],
                            "decision_reason": "Invalid unselected relation mapping.",
                        }
                    ],
                    "overall_summary": "Invalid mapping.",
                    "confidence": 0.8,
                    "warnings": [],
                }
            )

    def test_wiki_page_plan_rejects_unknown_extra_fields(self) -> None:
        with self.assertRaises(ValueError):
            WikiPagePlan.model_validate(
                {
                    "operations": [
                        {
                            "action": "create",
                            "target_page": None,
                            "page_dir": "pages",
                            "canonical_path": "Agent-Loop.md",
                            "title": "Agent Loop",
                            "knowledge_object": "Agent Loop",
                            "selected_claim_ids": ["claim_agent_loop_pattern"],
                            "source_digest_ids": ["sd_agent_loop"],
                            "candidate_pages": [],
                            "subject_kind": "legacy",
                            "decision_reason": "Legacy taxonomy field should not pass.",
                        }
                    ],
                    "overall_summary": "Invalid legacy field.",
                    "confidence": 0.8,
                    "warnings": [],
                }
            )

    def test_wiki_page_plan_drops_redundant_mixed_skip(self) -> None:
        plan = WikiPagePlan.model_validate(
            {
                "operations": [
                    {
                        "action": "skip",
                        "target_page": None,
                        "page_dir": None,
                        "title": "Skip",
                        "knowledge_object": "low value source",
                        "candidate_pages": [],
                        "decision_reason": "No durable knowledge.",
                    },
                    {
                        "action": "create",
                        "target_page": None,
                        "page_dir": "pages",
                        "title": "Agent Loop",
                        "knowledge_object": "Agent Loop",
                        "selected_claim_ids": ["claim_agent_loop"],
                        "source_digest_ids": ["sd_agent"],
                        "candidate_pages": [],
                        "decision_reason": "Durable knowledge.",
                    },
                ],
                "overall_summary": "Mixed plan with redundant skip.",
                "confidence": 0.5,
                "warnings": [],
            }
        )

        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].action, "create")
        self.assertIn("Dropped redundant skip operation", plan.warnings[0])

    def test_wiki_page_plan_accepts_skip_without_title(self) -> None:
        plan = WikiPagePlan.model_validate(
            {
                "operations": [
                    {
                        "action": "skip",
                        "target_page": None,
                        "page_dir": None,
                        "title": None,
                        "knowledge_object": None,
                        "candidate_pages": [],
                        "decision_reason": "No durable knowledge.",
                    }
                ],
                "overall_summary": "Skip low-value source.",
                "confidence": 0.5,
                "warnings": [],
            }
        )

        self.assertEqual(plan.operations[0].title, "Skipped source")
        self.assertEqual(plan.operations[0].knowledge_object, "No durable wiki object")

    def test_wiki_page_plan_requires_source_digest_trace_for_actionable_operations(self) -> None:
        with self.assertRaises(ValueError):
            WikiPagePlan.model_validate(
                {
                    "operations": [
                        {
                            "action": "create",
                            "target_page": None,
                            "page_dir": "sources",
                            "title": "Agent Source",
                            "knowledge_object": "Agent source digest",
                            "candidate_pages": [],
                            "decision_reason": "Source digest pages still require source trace.",
                        }
                    ],
                    "overall_summary": "Invalid source operation.",
                }
            )

    def test_wiki_page_plan_requires_claim_trace_for_non_source_operations(self) -> None:
        with self.assertRaises(ValueError):
            WikiPagePlan.model_validate(
                {
                    "operations": [
                        {
                            "action": "create",
                            "target_page": None,
                            "page_dir": "pages",
                            "title": "Agent Loop",
                            "knowledge_object": "Agent Loop",
                            "source_digest_ids": ["sd_agent"],
                            "candidate_pages": [],
                            "decision_reason": "Knowledge pages require selected claims.",
                        }
                    ],
                    "overall_summary": "Invalid non-source operation.",
                }
            )

    def test_wiki_page_plan_rejects_ingest_merge(self) -> None:
        with self.assertRaises(ValueError):
            WikiPagePlan.model_validate(
                {
                    "operations": [
                        {
                            "action": "merge",
                            "target_page": "Agent.md",
                            "page_dir": "pages",
                            "title": "Agent",
                            "knowledge_object": "Agent",
                            "candidate_pages": [],
                            "decision_reason": "Page consolidation belongs to lint maintenance.",
                        }
                    ],
                    "overall_summary": "Invalid merge.",
                    "confidence": 0.5,
                    "warnings": [],
                }
            )

    def test_wiki_draft_batch_accepts_atom_trace_fields(self) -> None:
        batch = WikiDraftBatch.model_validate(
            {
                "drafts": [
                    {
                        "operation_index": 0,
                        "write_action": "create",
                        "target_page": None,
                        "source_file": "raw/inbox/notes/Agent.md",
                        "title": "Agent Loop",
                        "page_dir": "pages",
                        "canonical_path": "Agent-Loop.md",
                        "question": "Agent Loop",
                        "summary": "Agent Loop is a control pattern.",
                        "synthesis": "Agent Loop coordinates tool use.",
                        "claims": ["C1. [[Agent Loop]] coordinates tool use."],
                        "source_digest_ids": [" sd_agent ", "sd_agent"],
                        "atom_ids": ["claim_agent_loop_cycle", " claim_agent_loop_cycle "],
                        "patches": [],
                        "confidence": 0.9,
                    }
                ],
                "batch_summary": "One draft.",
                "warnings": [],
            }
        )

        draft = batch.drafts[0]
        self.assertEqual(draft.source_digest_ids, ["sd_agent"])
        self.assertEqual(draft.canonical_path, "Agent-Loop.md")
        self.assertEqual(draft.atom_ids, ["claim_agent_loop_cycle"])
        self.assertEqual(draft.claims, ["C1. [[Agent Loop]] coordinates tool use."])
        self.assertEqual(draft.synthesis, "Agent Loop coordinates tool use.")

    def test_wiki_draft_batch_accepts_canonical_page_target_without_identity_hints(self) -> None:
        batch = WikiDraftBatch.model_validate(
            {
                "drafts": [
                    {
                        "operation_index": 0,
                        "write_action": "create",
                        "target_page": None,
                        "source_file": "raw/inbox/notes/RAG.md",
                        "title": "RAG 评估方法",
                        "page_dir": "pages",
                        "question": "RAG 评估应该关注什么？",
                        "summary": "RAG 评估同时关注检索和生成。",
                        "synthesis": "RAG 评估需要同时覆盖检索质量与生成质量。",
                        "patches": [],
                        "confidence": 0.87,
                    }
                ],
                "batch_summary": "One draft with optional identity hints omitted.",
                "warnings": [],
            }
        )

        draft = batch.drafts[0]
        self.assertEqual(draft.page_dir, "pages")
        self.assertEqual(draft.title, "RAG 评估方法")

    def test_wiki_draft_batch_schema_accepts_create_and_update(self) -> None:
        batch = WikiDraftBatch.model_validate(
            {
                "drafts": [
                    {
                        "operation_index": 0,
                        "write_action": "create",
                        "target_page": None,
                        "source_file": "raw/inbox/notes/Agent.md",
                        "title": "Agent Loop",
                        "page_dir": "pages",
                        "question": "Agent Loop 是什么？",
                        "summary": "Agent Loop 是智能体执行任务的基本控制循环。",
                        "synthesis": "Agent Loop 是感知、决策、行动和反馈的循环。",
                        "patches": [],
                        "confidence": 0.88,
                        "model_provider": "deepseek",
                        "model_name": "deepseek-chat",
                    },
                    {
                        "operation_index": 1,
                        "write_action": "update",
                        "target_page": "OpenClaw.md",
                        "source_file": "raw/inbox/notes/Agent.md",
                        "title": "OpenClaw",
                        "page_dir": "pages",
                        "question": "OpenClaw 如何使用 Agent Loop？",
                        "summary": "补充 OpenClaw 与 Agent Loop 的关系。",
                        "synthesis": "OpenClaw 使用消息总线和工具调用循环组织工程任务。",
                        "patches": [
                            {
                                "operation": "merge_list",
                                "section": "Claims",
                                "items": None,
                                "max_items": 0,
                            }
                        ],
                        "confidence": 0.82,
                        "model_provider": "deepseek",
                        "model_name": "deepseek-chat",
                    },
                ],
                "batch_summary": "Create concept and update entity relation.",
                "warnings": [],
            }
        )

        self.assertEqual(batch.drafts[0].write_action, "create")
        self.assertEqual(batch.drafts[1].patches[0].section, "Claims")
        self.assertEqual(batch.drafts[1].patches[0].items, [])
        self.assertEqual(batch.drafts[1].patches[0].max_items, 0)

    def test_wiki_draft_batch_requires_patch_for_update(self) -> None:
        with self.assertRaises(ValueError):
            WikiDraftBatch.model_validate(
                {
                    "drafts": [
                        {
                            "operation_index": 0,
                            "write_action": "update",
                            "target_page": "Agent Loop.md",
                            "source_file": "raw/inbox/notes/Agent.md",
                            "title": "Agent Loop",
                            "page_dir": "pages",
                            "question": "Agent Loop 是什么？",
                            "answer": "更新内容。",
                            "summary": "更新摘要。",
                            "patches": [],
                            "confidence": 0.8,
                            "model_provider": "deepseek",
                            "model_name": "deepseek-chat",
                        }
                    ],
                    "batch_summary": "Invalid update.",
                    "warnings": [],
                }
            )

    def test_wiki_draft_batch_rejects_json_patch_shape(self) -> None:
        with self.assertRaises(ValueError):
            WikiDraftBatch.model_validate(
                {
                    "drafts": [
                        {
                            "operation_index": 0,
                            "write_action": "update",
                            "target_page": "Agent Loop.md",
                            "source_file": "raw/inbox/notes/Agent.md",
                            "title": "Agent Loop",
                            "page_dir": "pages",
                            "question": "Agent Loop 是什么？",
                            "answer": "更新内容。",
                            "summary": "更新摘要。",
                            "patches": [
                                {
                                    "op": "replace",
                                    "path": "/Summary",
                                    "value": "New summary.",
                                }
                            ],
                            "confidence": 0.8,
                            "model_provider": "deepseek",
                            "model_name": "deepseek-chat",
                        }
                    ],
                    "batch_summary": "Invalid patch shape.",
                    "warnings": [],
                }
            )

    def test_wiki_draft_batch_accepts_empty_skip_batch(self) -> None:
        batch = WikiDraftBatch.model_validate(
            {
                "drafts": [],
                "batch_summary": "No durable wiki page is needed for this source.",
                "warnings": ["Skipped by page plan."],
            }
        )

        self.assertEqual(batch.drafts, [])

    def test_ingest_draft_review_schema_accepts_current_review_shape(self) -> None:
        review = IngestDraftReview.model_validate(
            {
                "schema_version": "ingest_draft_review.v2",
                "decisions": [
                    {
                        "operation_index": 0,
                        "decision": "approve",
                        "quality_score": 0.91,
                        "risk_level": "low",
                        "write_safety": "safe_create",
                        "reason": "The draft is source-supported and has a clear page boundary.",
                        "required_changes": [],
                        "dimension_scores": {
                            "source_trace": 0.9,
                            "atom_coverage": 0.9,
                            "source_support": 0.94,
                            "page_boundary": 0.9,
                            "identity_fit": 0.92,
                            "duplication_risk": 0.86,
                            "relation_quality": 0.82,
                            "synthesis_quality": 0.88,
                            "maintainability": 0.9,
                            "update_safety": 0.95,
                        },
                        "checks": {
                            "operation_aligned": True,
                            "source_trace_complete": True,
                            "atom_coverage_sufficient": True,
                            "page_boundary_clear": True,
                            "identity_fit": True,
                            "source_supported": True,
                            "not_duplicate": True,
                            "relation_quality": True,
                            "synthesis_quality": True,
                            "maintainable": True,
                            "update_safe": True,
                            "write_safe": True,
                        },
                    }
                ],
                "batch_decision": "approve",
                "summary": "The batch is safe to write.",
                "warnings": [],
            }
        )

        self.assertEqual(review.decisions[0].write_safety, "safe_create")

    def test_maintenance_candidates_schema_accepts_structural_and_quality_output(self) -> None:
        candidates = MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "structural:Agent.md:broken_link:0",
                        "source": "structural",
                        "target_page": "Agent.md",
                        "issue_type": "broken_link",
                        "severity": "high",
                        "confidence": 0.92,
                        "risk_hint": "low",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [
                            {
                                "kind": "scan_issue",
                                "ref": "Agent.md",
                                "quote": "Broken wikilink: [[Missing Page]]",
                            }
                        ],
                        "recommended_action": {
                            "action": "replace_wikilink",
                            "params": {"old_target": "Missing Page", "new_target": "Agent Loop"},
                        },
                        "expected_effect": "The broken link will point at an existing page.",
                        "review_notes": "Verify the replacement target is the intended concept.",
                    }
                ],
                "page_reviews": [
                    {
                        "path": "Agent.md",
                        "verdict": "needs_maintenance",
                        "overall_score": 0.72,
                        "dimension_reviews": [
                            {
                                "dimension": "graph_integration",
                                "score": 0.55,
                                "severity": "medium",
                                "finding": "The page links to a missing concept.",
                                "evidence": "[[Missing Page]]",
                                "recommendation": "Replace the broken link.",
                            }
                        ],
                    }
                ],
                "summary": "One structural candidate.",
                "warnings": [],
            }
        )

        self.assertEqual(candidates.candidates[0].recommended_action.action, "replace_wikilink")
        self.assertEqual(candidates.page_reviews[0].verdict, "needs_maintenance")

    def test_lint_maintenance_review_schema_accepts_current_review_shape(self) -> None:
        review = LintMaintenanceReview.model_validate(
            {
                "schema_version": "lint_maintenance_review.v1",
                "decisions": [
                    {
                        "operation_index": 0,
                        "decision": "approve",
                        "necessity": "necessary",
                        "correctness": "correct",
                        "completeness": "complete",
                        "executor_fit": "supported_by_wiki_operation",
                        "risk_level": "low",
                        "confidence": 0.9,
                        "reason": "The operation has explicit scan evidence and parameters.",
                        "constraints": ["Do not modify unrelated sections."],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved one low-risk operation.",
                "warnings": [],
            }
        )

        self.assertEqual(review.decisions[0].executor_fit, "supported_by_wiki_operation")


if __name__ == "__main__":
    unittest.main()
