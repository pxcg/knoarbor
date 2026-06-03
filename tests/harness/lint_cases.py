from __future__ import annotations

from pathlib import Path

from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview


def create_lint_fixture_vault(vault: Path) -> None:
    (vault / "concepts").mkdir(parents=True)
    (vault / "entities").mkdir()
    (vault / "sources").mkdir()
    (vault / "raw" / "notes").mkdir(parents=True)
    (vault / "raw" / "notes" / "agent.md").write_text("# Agent Loop Source\n\nOriginal source.", encoding="utf-8")

    (vault / "concepts" / "Agent-Loop.md").write_text(
        "\n".join(
            [
                "---",
                "created: 2026-05-01",
                "updated: 2026-05-01",
                "type: concept",
                "status: draft",
                "source: raw/notes/agent.md",
                "content_hash: agent-loop",
                "---",
                "# Agent Loop",
                "",
                "## Summary",
                "",
                "Agent loop coordinates observe, reason, act, and feedback.",
                "",
                "## Answer",
                "",
                "Agent loop pages should link to the source digest and related implementations.",
                "",
                "## Key Points",
                "",
                "- It repeats observation and action.",
                "",
                "## Related Pages",
                "",
                "- [[Missing Page]]",
                "",
                "## Tags",
                "",
                "- agent",
                "",
                "## Source",
                "",
                "- raw/notes/agent.md",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (vault / "entities" / "OpenClaw.md").write_text(
        "\n".join(
            [
                "---",
                "created: 2026-05-01",
                "updated: 2026-05-01",
                "type: entity",
                "status: draft",
                "source: raw/notes/openclaw.md",
                "content_hash: openclaw",
                "---",
                "# OpenClaw",
                "",
                "## Summary",
                "",
                "OpenClaw is an agent system related to agent loop control.",
                "",
                "## Answer",
                "",
                "OpenClaw uses agent control loops.",
                "",
                "## Key Points",
                "",
                "- It is relevant context for Agent Loop.",
                "",
                "## Related Pages",
                "",
                "- 暂无关联知识",
                "",
                "## Tags",
                "",
                "- agent",
                "",
                "## Source",
                "",
                "- raw/notes/openclaw.md",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (vault / "sources" / "Agent-Loop-Source.md").write_text(
        "\n".join(
            [
                "---",
                "created: 2026-05-01",
                "updated: 2026-05-01",
                "type: source",
                "status: draft",
                "source: raw/notes/agent.md",
                "content_hash: agent-source",
                "---",
                "# Agent Loop Source",
                "",
                "## Summary",
                "",
                "Source digest for agent loop notes.",
                "",
                "## Answer",
                "",
                "This source digest records provenance for the agent loop page.",
                "",
                "## Key Points",
                "",
                "- Source provenance.",
                "",
                "## Related Pages",
                "",
                "- 暂无关联知识",
                "",
                "## Tags",
                "",
                "- source",
                "",
                "## Source",
                "",
                "- raw/notes/agent.md",
                "",
            ]
        ),
        encoding="utf-8",
    )


class LintStructuralFixtureWorkflow:
    def diagnose_structural(self, scan_payload: dict[str, object], *, max_tokens: int | None = None) -> MaintenanceCandidates:
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "provenance:concepts/Agent-Loop.md:knowledge_missing_source_digest_link:0",
                        "source": "provenance",
                        "target_page": "concepts/Agent-Loop.md",
                        "issue_type": "knowledge_missing_source_digest_link",
                        "severity": "medium",
                        "confidence": 0.95,
                        "risk_hint": "low",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [
                            {
                                "kind": "scan_issue",
                                "ref": "concepts/Agent-Loop.md",
                                "quote": "Generated knowledge page does not link back to its matching source digest.",
                            }
                        ],
                        "recommended_action": {
                            "action": "attach_source_digest",
                            "params": {
                                "related_pages": ["sources/Agent-Loop-Source.md"],
                            },
                        },
                        "related_pages": ["sources/Agent-Loop-Source.md"],
                        "expected_effect": "Connect the concept page back to its source digest.",
                        "review_notes": "The source digest exists in the fixture vault.",
                    }
                ],
                "summary": "Attach one missing source digest link.",
                "warnings": [],
            }
        )

    def diagnose_quality(self, quality_payload: dict[str, object], *, max_tokens: int | None = None) -> MaintenanceCandidates:
        return MaintenanceCandidates(candidates=[], page_reviews=[], summary="No quality candidates.", warnings=[])

    def review(self, review_payload: dict[str, object], *, max_tokens: int | None = None) -> LintMaintenanceReview:
        return LintMaintenanceReview.model_validate(
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
                        "confidence": 0.95,
                        "reason": "The source digest target is explicit and exists.",
                        "constraints": ["Do not create a new page."],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved deterministic wiki operation.",
                "warnings": [],
            }
        )
