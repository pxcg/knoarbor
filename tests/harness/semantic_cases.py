from __future__ import annotations

from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin


def markdown_source_document(
    *,
    source_id: str = "markdown:agent",
    title: str = "Agent",
    raw_path: str = "raw/inbox/notes/Agent.md",
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


def lint_candidates_output() -> dict[str, object]:
    return {
        "output": {
            "schema_version": "maintenance_candidates.v1",
            "candidates": [
                {
                    "candidate_id": "structural:Agent.md:broken_link:0",
                    "source": "structural",
                    "target_page": "Agent.md",
                    "issue_type": "broken_link",
                    "severity": "high",
                    "confidence": 0.9,
                    "risk_hint": "low",
                    "executor_hint": "governance_request",
                    "evidence": [
                        {
                            "kind": "scan_issue",
                            "ref": "Agent.md",
                            "quote": "[[Missing Page]]",
                        }
                    ],
                    "recommended_action": {
                        "action": "replace_wikilink",
                        "params": {"old_target": "Missing Page", "new_target": "Agent Loop"},
                    },
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
                    "executor_fit": "supported_by_governance_request",
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
