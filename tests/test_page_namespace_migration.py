from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from knoarbor.storage.knowledge_atom_index import knowledge_atom_index_path
from knoarbor.storage.page_namespace_migration import migrate_page_namespace
from knoarbor.storage.wiki_index import machine_index_dir


def _page(title: str, body: str = "") -> str:
    return f"""---
created: 2026-01-01 00:00:00
updated: 2026-01-01 00:00:00
type: concept
status: draft
---
# {title}

## Summary

{body or title}

## Related Pages

- 暂无关联知识
"""


class PageNamespaceMigrationTests(unittest.TestCase):
    def test_dry_run_plans_legacy_knowledge_pages_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            root = vault / "pages"
            (root / "concepts").mkdir(parents=True)
            (root / "sources").mkdir(parents=True)
            (root / "concepts" / "Agent-Loop.md").write_text(_page("Agent Loop"), encoding="utf-8")
            (root / "sources" / "Agent-Loop-Source.md").write_text(_page("Agent Loop Source"), encoding="utf-8")

            result = migrate_page_namespace(vault)

            self.assertTrue(result.dry_run)
            self.assertEqual(len(result.planned_moves), 1)
            self.assertEqual(result.planned_moves[0].source_path, "concepts/Agent-Loop.md")
            self.assertEqual(result.planned_moves[0].target_path, "Agent-Loop.md")
            self.assertTrue((root / "concepts" / "Agent-Loop.md").exists())
            self.assertFalse((root / "Agent-Loop.md").exists())

    def test_dry_run_reports_flat_namespace_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            root = vault / "pages"
            (root / "concepts").mkdir(parents=True)
            (root / "entities").mkdir(parents=True)
            (root / "concepts" / "Agent.md").write_text(_page("Agent Concept"), encoding="utf-8")
            (root / "entities" / "Agent.md").write_text(_page("Agent Entity"), encoding="utf-8")

            result = migrate_page_namespace(vault)

            self.assertFalse(result.can_apply)
            self.assertEqual(len(result.conflicts), 2)
            self.assertEqual({conflict.target_path for conflict in result.conflicts}, {"Agent.md"})

    def test_apply_moves_pages_rewrites_links_and_atom_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            root = vault / "pages"
            (root / "concepts").mkdir(parents=True)
            (root / "workflows").mkdir(parents=True)
            (root / "sources").mkdir(parents=True)
            (root / "concepts" / "Agent-Loop.md").write_text(
                _page("Agent Loop", "See [[workflows/Agent-Workflow|workflow]]."),
                encoding="utf-8",
            )
            (root / "workflows" / "Agent-Workflow.md").write_text(
                _page("Agent Workflow", "Related to [[concepts/Agent-Loop|Agent Loop]]."),
                encoding="utf-8",
            )
            (root / "sources" / "Agent-Source.md").write_text(
                _page("Agent Source", "- [[concepts/Agent-Loop|Agent Loop]]"),
                encoding="utf-8",
            )
            atom_path = knowledge_atom_index_path(vault)
            atom_path.parent.mkdir(parents=True, exist_ok=True)
            atom_path.write_text(
                json.dumps(
                    {
                        "schema_version": "knowledge_atom_record.v1",
                        "source_digest_id": "source:agent",
                        "atom_id": "atom-1",
                        "atom_type": "claim",
                        "text": "Agent Loop is iterative.",
                        "payload": {},
                        "evidence": [],
                        "page_paths": ["concepts/Agent-Loop.md"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            result = migrate_page_namespace(vault, apply=True)

            self.assertFalse(result.dry_run)
            self.assertEqual(len(result.moved_paths), 2)
            self.assertFalse((root / "concepts" / "Agent-Loop.md").exists())
            self.assertTrue((root / "Agent-Loop.md").exists())
            self.assertIn("canonical_path: Agent-Loop.md", (root / "Agent-Loop.md").read_text(encoding="utf-8"))
            self.assertIn('legacy_paths: ["concepts/Agent-Loop.md"]', (root / "Agent-Loop.md").read_text(encoding="utf-8"))
            self.assertIn("[[Agent-Loop|Agent Loop]]", (root / "sources" / "Agent-Source.md").read_text(encoding="utf-8"))
            atom_record = json.loads(atom_path.read_text(encoding="utf-8").strip())
            self.assertEqual(atom_record["page_paths"], ["Agent-Loop.md"])
            self.assertTrue((machine_index_dir(vault) / "pages.json").exists())


if __name__ == "__main__":
    unittest.main()
