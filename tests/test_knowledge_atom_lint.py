from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.maintenance.wiki_lint import lint_vault
from knoarbor.storage.knowledge_atom_index import KnowledgeAtomPageRef, upsert_knowledge_atom_batch


def _write_page(vault: Path) -> None:
    page = vault / "pages" / "concepts" / "Agent-Loop.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        """# Agent Loop

---
created: 2026-01-01 00:00:00
updated: 2026-01-01 00:00:00
type: concept
status: draft
source: raw/notes/agent.md
content_hash: test
confidence: 0.80
model_provider: test
model_name: unit
source_digest_ids: ["sd_agent"]
atom_ids: ["claim_missing_support", "rel_supports", "rel_contradicts"]
---

## Summary

Agent loop summary.

## Source Focus

Agent loop.

## Answer

Agent loop answer.

## Key Points

- Agent loop point.

## Related Pages

- 暂无关联知识

## Tags

- agent

## Source

- raw/notes/agent.md
""",
        encoding="utf-8",
    )


def _evidence() -> KnowledgeEvidenceSpan:
    return KnowledgeEvidenceSpan(source_digest_id="sd_agent", excerpt="Agent loop evidence.")


class KnowledgeAtomLintTests(unittest.TestCase):
    def test_lint_reports_atom_support_and_conflict_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _write_page(vault)
            subject = KnowledgeAtomObject(object_type="concept", name="Agent Loop")
            target = KnowledgeAtomObject(object_type="concept", name="Workflow")
            upsert_knowledge_atom_batch(
                vault,
                KnowledgeAtomBatch(
                    source_digest_id="sd_agent",
                    claims=[
                        KnowledgeClaim(
                            id="claim_missing_support",
                            claim="Agent loop depends on missing support.",
                            claim_type="assessment",
                            supporting_fact_ids=["missing_fact"],
                        )
                    ],
                    relations=[
                        KnowledgeRelation(
                            id="rel_supports",
                            subject=subject,
                            predicate="supports",
                            object=target,
                            evidence=[_evidence()],
                        ),
                        KnowledgeRelation(
                            id="rel_contradicts",
                            subject=subject,
                            predicate="contradicts",
                            object=target,
                            evidence=[_evidence()],
                        ),
                    ],
                ),
                [
                    KnowledgeAtomPageRef(
                        path="concepts/Agent-Loop.md",
                        source_digest_ids=["sd_agent"],
                        atom_ids=["claim_missing_support", "rel_supports", "rel_contradicts"],
                    )
                ],
            )

            issues, stats = lint_vault(vault)

        codes = {issue.code for issue in issues}
        self.assertIn("atom_claim_missing_support", codes)
        self.assertIn("atom_conflicting_relation", codes)
        self.assertEqual(stats["knowledge_atom_index"]["record_count"], 3)
        self.assertEqual(stats["knowledge_atom_index"]["issue_count"], 2)


if __name__ == "__main__":
    unittest.main()
