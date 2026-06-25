from __future__ import annotations

from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin


def markdown_source_document(
    *,
    source_id: str = "markdown:agent",
    title: str = "Agent",
    raw_path: str = "raw/notes/Agent.md",
    text: str = "# Agent\n\nAgent loop.",
) -> SourceDocument:
    return SourceDocument(
        source_id=source_id,
        source_type="markdown",
        origin=SourceOrigin(connector="markdown", uri=f"file:///{raw_path}", raw_path=raw_path),
        content=SourceContent(format="markdown", text=text),
        metadata={"title": title},
        fingerprint=SourceFingerprint(content_hash=source_id.split(":", 1)[-1], connector_version="markdown@1"),
    )


def source_normalize_output(*, title: str = "Agent", content: str = "Agent loop is observe, decide, act, feedback.") -> dict[str, object]:
    return {
        "output": {
            "schema_version": "knowledge_extract.v1",
            "source": {
                "source_type": "markdown",
                "source_app": "markdown",
                "source_id": "markdown:agent",
                "source_path": "raw/notes/Agent.md",
                "title": title,
                "created_at": None,
                "updated_at": None,
            },
            "content_units": [
                {
                    "index": 0,
                    "unit_type": "note",
                    "role": "note",
                    "title": title,
                    "content": content,
                    "timestamp": None,
                    "is_primary": True,
                    "metadata": {},
                }
            ],
            "compile_context": {
                "primary_content": content,
                "supporting_evidence": [],
                "links": [],
                "latest_unit_indexes": [0],
            },
            "confidence": 0.9,
            "warnings": [],
        }
    }


def wiki_page_plan_output() -> dict[str, object]:
    return {
        "output": {
            "operations": [
                {
                    "action": "create",
                    "target_page": None,
                    "page_dir": "concepts",
                    "canonical_path": "Agent-Loop.md",
                    "legacy_paths": ["concepts/Agent-Loop.md"],
                    "page_kind": "concept",
                    "subject_kind": "control_pattern",
                    "facets": ["agent_loop", "agent_architecture"],
                    "title": "Agent Loop",
                    "knowledge_object": "Agent Loop",
                    "selected_claim_ids": ["claim_agent_loop_control_pattern"],
                    "selected_relation_ids": ["rel_agent_loop_mentions_control"],
                    "source_digest_ids": ["sd_test_agent"],
                    "related_pages": [],
                    "candidate_pages": [],
                    "decision_reason": "The source defines a durable concept.",
                }
            ],
            "overall_summary": "Create one concept page.",
            "confidence": 0.9,
            "warnings": [],
        }
    }


def wiki_atom_extract_output() -> dict[str, object]:
    return {
        "output": {
            "schema_version": "knowledge_atoms.v2",
            "source_digest_id": "sd_test_agent",
            "entities": [
                {
                    "object_type": "knowledge_object",
                    "name": "Agent Loop",
                    "atom_id": "entity_agent_loop",
                },
                {
                    "object_type": "knowledge_object",
                    "name": "Agent Control",
                    "atom_id": "entity_agent_control",
                },
            ],
            "claims": [
                {
                    "id": "claim_agent_loop_control_pattern",
                    "claim": "Agent loop is an observe, decide, act, feedback cycle and a reusable control pattern for agents.",
                    "claim_type": "definition",
                    "stance": "asserted",
                    "evidence": [
                        {
                            "source_digest_id": "sd_test_agent",
                            "source_path": "raw/notes/Agent.md",
                            "source_unit_index": 0,
                            "excerpt": "Agent loop is observe, decide, act, feedback.",
                        }
                    ],
                    "entity_names": ["Agent Loop", "Agent Control"],
                    "confidence": 0.9,
                }
            ],
            "relations": [
                {
                    "id": "rel_agent_loop_mentions_control",
                    "subject": {"object_type": "knowledge_object", "name": "Agent Loop"},
                    "predicate": "includes",
                    "object": {"object_type": "knowledge_object", "name": "Agent Control"},
                    "source_claim_ids": ["claim_agent_loop_control_pattern"],
                    "evidence": [],
                    "reason": "Agent loop describes a control cycle.",
                    "confidence": 0.8,
                }
            ],
            "evidence": [
                {
                    "source_digest_id": "sd_test_agent",
                    "source_path": "raw/notes/Agent.md",
                    "source_unit_index": 0,
                    "excerpt": "Agent loop is observe, decide, act, feedback.",
                }
            ],
            "warnings": [],
        }
    }


def wiki_draft_batch_output() -> dict[str, object]:
    return {
        "output": {
            "drafts": [
                {
                    "operation_index": 0,
                    "write_action": "create",
                    "target_page": None,
                    "source_file": "raw/notes/Agent.md",
                    "title": "Agent Loop",
                    "page_dir": "concepts",
                    "canonical_path": "Agent-Loop.md",
                    "legacy_paths": ["concepts/Agent-Loop.md"],
                    "page_kind": "concept",
                    "subject_kind": "control_pattern",
                    "facets": ["agent_loop", "agent_architecture"],
                    "question": "Agent Loop",
                    "summary": "Agent Loop is a basic control cycle for agents.",
                    "claims": ["C1. [[Agent Loop]] is an observe, decide, act, feedback cycle."],
                    "entities": ["[[Agent Loop]]"],
                    "relations": ["[[Agent Loop]] | includes | [[Agent Control]] | C1"],
                    "evidence": ["C1 | sd_test_agent | unit:0 | source states the loop cycle | high"],
                    "synthesis": "Agent Loop is an observe, decide, act, feedback cycle.",
                    "source_digest_ids": ["sd_test_agent"],
                    "atom_ids": [
                        "claim_agent_loop_control_pattern",
                        "rel_agent_loop_mentions_control",
                    ],
                    "patches": [],
                    "confidence": 0.9,
                    "model_provider": "fake",
                    "model_name": "unit",
                }
            ],
            "batch_summary": "One concept draft.",
            "warnings": [],
        }
    }


def ingest_review_output() -> dict[str, object]:
    return {
        "output": {
            "schema_version": "ingest_draft_review.v2",
            "decisions": [
                {
                    "operation_index": 0,
                    "decision": "approve",
                    "quality_score": 0.9,
                    "risk_level": "low",
                    "write_safety": "safe_create",
                    "reason": "The draft is source-supported.",
                    "required_changes": [],
                    "dimension_scores": {
                        "source_trace": 0.9,
                        "atom_coverage": 0.9,
                        "source_support": 0.9,
                        "page_boundary": 0.9,
                        "identity_fit": 0.9,
                        "duplication_risk": 0.9,
                        "relation_quality": 0.9,
                        "synthesis_quality": 0.9,
                        "maintainability": 0.9,
                        "update_safety": 0.9,
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
            "summary": "Approved.",
            "warnings": [],
        }
    }


def lint_candidates_output() -> dict[str, object]:
    return {
        "output": {
            "schema_version": "maintenance_candidates.v1",
            "candidates": [
                {
                    "candidate_id": "structural:concepts/Agent.md:broken_link:0",
                    "source": "structural",
                    "target_page": "concepts/Agent.md",
                    "issue_type": "broken_link",
                    "severity": "high",
                    "confidence": 0.9,
                    "risk_hint": "low",
                    "executor_hint": "deterministic_wiki_operation",
                    "evidence": [
                        {
                            "kind": "scan_issue",
                            "ref": "concepts/Agent.md",
                            "quote": "[[Missing Page]]",
                        }
                    ],
                    "recommended_action": {
                        "action": "replace_wikilink",
                        "params": {"old_target": "Missing Page", "new_target": "concepts/Agent Loop"},
                    },
                    "related_pages": ["concepts/Agent Loop.md"],
                    "expected_effect": "Fix broken link.",
                    "review_notes": "Verify target exists.",
                }
            ],
            "page_reviews": [],
            "summary": "One candidate.",
            "warnings": [],
        }
    }


def lint_review_output() -> dict[str, object]:
    return {
        "output": {
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
                    "reason": "The operation is explicit and supported.",
                    "constraints": [],
                    "required_followups": [],
                }
            ],
            "summary": "Approved.",
            "warnings": [],
        }
    }


def lint_draft_batch_output() -> dict[str, object]:
    return {
        "output": {
            "drafts": [
                {
                    "operation_index": 0,
                    "write_action": "create",
                    "target_page": None,
                    "source_file": "raw/notes/Agent.md",
                    "title": "Agent Source Digest",
                    "page_dir": "sources",
                    "canonical_path": "sources/Agent-Source-Digest.md",
                    "legacy_paths": [],
                    "page_kind": "source_digest",
                    "subject_kind": "source_digest",
                    "facets": ["source_digest"],
                    "question": "Source digest",
                    "summary": "Source digest for Agent notes.",
                    "synthesis": "This source describes Agent Loop.",
                    "patches": [],
                    "confidence": 0.8,
                    "model_provider": "fake",
                    "model_name": "unit",
                }
            ],
            "batch_summary": "One draft.",
            "warnings": [],
        }
    }
