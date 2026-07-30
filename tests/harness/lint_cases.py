from __future__ import annotations

from pathlib import Path

from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview


def create_lint_fixture_vault(vault: Path) -> None:
    (vault / "wiki" / "pages").mkdir(parents=True)
    (vault / "wiki" / "sources").mkdir(parents=True)
    (vault / "raw" / "inbox" / "notes").mkdir(parents=True)
    (vault / "raw" / "inbox" / "notes" / "agent.md").write_text("# Agent Loop Source\n\nOriginal source.", encoding="utf-8")

    (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
        "\n".join(
            [
                "---",
                "created: 2026-05-01",
                "updated: 2026-05-01",
                "content_hash: agent-loop",
                "---",
                "# Agent Loop",
                "",
                "## Summary",
                "",
                "Agent loop coordinates observe, reason, act, and feedback.",
                "",
                "## Claims",
                "",
                "- C1: Agent loop coordinates observe, reason, act, and feedback.",
                "",
                "## Entities",
                "",
                "- Agent Loop",
                "",
                "## Relations",
                "",
                "- [[Agent Loop]] | coordinates | [[Feedback]] | C1",
                "",
                "## Evidence",
                "",
                "| Claim | Source | Range | Basis |",
                "|---|---|---|---|",
                "| C1 | raw/inbox/notes/agent.md | unit:0 | Original source. |",
                "",
                "## Synthesis",
                "",
                "Agent loop pages should record source support and implementation context.",
                "",
                "## Source",
                "",
                "- raw/inbox/notes/agent.md",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (vault / "wiki" / "pages" / "OpenClaw.md").write_text(
        "\n".join(
            [
                "---",
                "created: 2026-05-01",
                "updated: 2026-05-01",
                "content_hash: openclaw",
                "---",
                "# OpenClaw",
                "",
                "## Summary",
                "",
                "OpenClaw is an agent system related to agent loop control.",
                "",
                "## Claims",
                "",
                "- C1: OpenClaw uses agent control loops.",
                "",
                "## Entities",
                "",
                "- OpenClaw",
                "- Agent Loop",
                "",
                "## Relations",
                "",
                "- [[OpenClaw]] | uses | [[Agent Loop]] | C1",
                "",
                "## Evidence",
                "",
                "| Claim | Source | Range | Basis |",
                "|---|---|---|---|",
                "| C1 | raw/inbox/notes/openclaw.md | unit:0 | Fixture support. |",
                "",
                "## Synthesis",
                "",
                "OpenClaw uses agent control loops.",
                "",
                "## Source",
                "",
                "- raw/inbox/notes/openclaw.md",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (vault / "wiki" / "sources" / "Agent-Loop-Source.md").write_text(
        "\n".join(
            [
                "---",
                "created: 2026-05-01",
                "updated: 2026-05-01",
                "content_hash: agent-source",
                "---",
                "# Agent Loop Source",
                "",
                "## Audit Summary",
                "",
                "Source record for agent loop notes.",
                "",
                "## Raw Source",
                "",
                "- raw/inbox/notes/agent.md",
                "",
                "## Source Units",
                "",
                "- U1: Agent loop notes.",
                "",
                "## Contribution Map",
                "",
                "- Agent-Loop.md: supports C1",
                "",
                "## Unresolved Items",
                "",
                "- None",
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
                        "candidate_id": "provenance:Agent-Loop.md:knowledge_missing_source_record_link:0",
                        "source": "provenance",
                        "target_page": "Agent-Loop.md",
                        "issue_type": "knowledge_missing_source_record_link",
                        "severity": "medium",
                        "confidence": 0.95,
                        "risk_hint": "low",
                        "executor_hint": "governance_request",
                        "evidence": [
                            {
                                "kind": "scan_issue",
                                "ref": "Agent-Loop.md",
                                "quote": "Generated knowledge page does not link back to its matching source record.",
                            }
                        ],
                        "recommended_action": {
                            "action": "record_source_record",
                            "params": {
                                "source_record": "sources/Agent-Loop-Source.md",
                            },
                        },
                        "expected_effect": "Connect the concept page back to its source record.",
                        "review_notes": "The source record exists in the fixture vault.",
                    }
                ],
                "summary": "Attach one missing source record link.",
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
                        "executor_fit": "supported_by_governance_request",
                        "risk_level": "low",
                        "confidence": 0.95,
                        "reason": "The source record target is explicit and exists.",
                        "constraints": ["Do not create a new page."],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved deterministic wiki operation.",
                "warnings": [],
            }
        )
