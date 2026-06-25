from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.storage import ensure_machine_index, index_entry, is_machine_index_stale, machine_index_dir, update_index, wiki_link_for_path


class WikiIndexStorageTests(unittest.TestCase):
    def test_update_index_catalogs_generated_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "pages" / "concepts").mkdir(parents=True)
            page = vault / "pages" / "concepts" / "Agent.md"
            page.write_text(
                "---\ntype: concept\nstatus: draft\ntags: agent, loop\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n",
                encoding="utf-8",
            )

            update_index(vault)
            manifest = json.loads((machine_index_dir(vault) / "manifest.json").read_text(encoding="utf-8"))
            graph = json.loads((machine_index_dir(vault) / "graph_index.json").read_text(encoding="utf-8"))
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            search = json.loads((machine_index_dir(vault) / "search.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], "knoarbor_index.v1")
        self.assertGreaterEqual(manifest["page_count"], 1)
        self.assertEqual(graph["schema_version"], "knoarbor_graph_index.v1")
        self.assertEqual(pages["pages"][0]["path"], "concepts/Agent.md")
        self.assertEqual(search["entries"][0]["title"], "Agent")

    def test_machine_index_records_links_and_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "pages" / "concepts").mkdir(parents=True)
            (vault / "pages" / "sources").mkdir(parents=True)
            (vault / "pages" / "sources" / "Source.md").write_text("# Source\n", encoding="utf-8")
            (vault / "pages" / "concepts" / "Agent.md").write_text(
                "---\ntype: concept\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nLinks to [[sources/Source|source]].\n",
                encoding="utf-8",
            )

            update_index(vault)
            links = json.loads((machine_index_dir(vault) / "links.json").read_text(encoding="utf-8"))
            sources = json.loads((machine_index_dir(vault) / "sources.json").read_text(encoding="utf-8"))

        self.assertEqual(links["links"][0]["target_path"], "sources/Source.md")
        self.assertEqual(sources["sources"][0]["source"], "raw/notes/agent.md")

    def test_graph_index_records_entities_relations_and_evidence_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "pages").mkdir()
            (vault / "pages" / "Agent-Loop.md").write_text(
                "---\ncreated: 2026-01-01 00:00:00\nupdated: 2026-01-01 00:00:00\ncontent_hash: abc\n---\n"
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop coordinates model and tool execution.\n\n"
                "## Claims\n\n- C1: [[Agent Loop]] coordinates [[Tool Execution]].\n\n"
                "## Entities\n\n- [[Agent Loop]]\n- [[Tool Execution]]\n\n"
                "## Relations\n\n| Subject | Predicate | Object | Based on |\n|---|---|---|---|\n| [[Agent Loop]] | coordinates | [[Tool Execution]] | C1 |\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | sources/Agent-Loop-Source.md | section:Loop | source states this directly | high |\n\n"
                "## Synthesis\n\nAgent loop is a runtime control pattern.\n",
                encoding="utf-8",
            )

            update_index(vault)
            graph = json.loads((machine_index_dir(vault) / "graph_index.json").read_text(encoding="utf-8"))

        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertIn("Agent Loop", nodes)
        self.assertIn("Tool Execution", nodes)
        self.assertEqual(
            graph["edges"][0],
            {
                "source": "Agent Loop",
                "predicate": "coordinates",
                "target": "Tool Execution",
                "page": "Agent-Loop.md",
                "claim": "C1",
            },
        )
        self.assertEqual(graph["sources"][0]["source"], "sources/Agent-Loop-Source.md")
        self.assertEqual(graph["sources"][0]["pages"], ["Agent-Loop.md"])

    def test_machine_index_emits_page_identity_fields_for_legacy_and_unified_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "pages" / "concepts").mkdir(parents=True)
            (vault / "pages" / "concepts" / "Agent-Loop.md").write_text(
                "---\ntype: concept\ntags: agent, workflow\n---\n"
                "# Agent Loop\n\n## Summary\n\nLegacy typed page.\n\n## Claims\n\n- Agent loops coordinate tools.\n",
                encoding="utf-8",
            )
            (vault / "pages" / "OpenClaw.md").write_text(
                "---\npage_kind: entity\nfacets: agent_platform, workflow-pattern\nlegacy_paths: entities/OpenClaw.md\n---\n"
                "# OpenClaw\n\n## Summary\n\nCanonical unified page.\n",
                encoding="utf-8",
            )

            update_index(vault)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            records = {record["path"]: record for record in pages["pages"]}

        self.assertEqual(pages["schema_version"], "machine_pages.v2")
        self.assertEqual(records["concepts/Agent-Loop.md"]["schema_version"], "machine_page.v2")
        self.assertEqual(records["concepts/Agent-Loop.md"]["canonical_path"], "concepts/Agent-Loop.md")
        self.assertEqual(records["concepts/Agent-Loop.md"]["page_kind"], "concept")
        self.assertEqual(records["concepts/Agent-Loop.md"]["role"], "knowledge_page")
        self.assertIn("claims", records["concepts/Agent-Loop.md"]["facets"])
        self.assertEqual(records["OpenClaw.md"]["directory"], "pages")
        self.assertEqual(records["OpenClaw.md"]["canonical_path"], "OpenClaw.md")
        self.assertEqual(records["OpenClaw.md"]["legacy_paths"], ["entities/OpenClaw.md"])
        self.assertEqual(records["OpenClaw.md"]["page_kind"], "entity")
        self.assertIn("agent_platform", records["OpenClaw.md"]["facets"])

    def test_update_index_keeps_generated_views_virtual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "pages"
            sources = vault / "pages" / "sources"
            pages.mkdir(parents=True)
            sources.mkdir(parents=True)
            (pages / "Agent-Loop.md").write_text(
                "---\ntype: page\npage_kind: concept\nfacets: [agent-loop]\n---\n"
                "# Agent Loop\n\n## Summary\n\nAgent loop coordinates model and tool execution.\n",
                encoding="utf-8",
            )
            (sources / "Agent-Loop-Source.md").write_text(
                "---\ntype: source\npage_kind: source_digest\nrole: source_digest\n---\n"
                "# Agent Loop Source\n\n## Summary\n\nSource digest for agent loop notes.\n",
                encoding="utf-8",
            )

            update_index(vault)
            pages_index = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            indexed_paths = {record["path"] for record in pages_index["pages"]}

        self.assertFalse((pages / "_views").exists())
        self.assertNotIn("_views/Home.md", indexed_paths)
        self.assertEqual(indexed_paths, {"Agent-Loop.md", "sources/Agent-Loop-Source.md"})

    def test_machine_index_stale_detection_refreshes_after_page_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text("# Agent\n", encoding="utf-8")

            update_index(vault)
            self.assertFalse(is_machine_index_stale(vault))
            (vault / "concepts" / "Agent.md").write_text("# Agent\n\n## Summary\n\nUpdated.", encoding="utf-8")

            self.assertTrue(is_machine_index_stale(vault))
            ensure_machine_index(vault)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))

        self.assertEqual(pages["pages"][0]["summary"], "Updated.")

    def test_update_index_skips_maintenance_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "maintenance").mkdir()
            (vault / "maintenance" / "lint_run_report_20260521_123244.md").write_text(
                "# Lint Run Report\n\nRuntime maintenance artifact.",
                encoding="utf-8",
            )

            update_index(vault)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            indexed_paths = {record["path"] for record in pages["pages"]}

        self.assertFalse(any("lint_run_report" in path for path in indexed_paths))
        self.assertFalse(any(path.startswith("maintenance/") for path in indexed_paths))

    def test_index_entry_and_wikilink_use_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "entities").mkdir()
            page = vault / "entities" / "MiniMind.md"
            page.write_text("# MiniMind\n\n## Summary\n\nA small model project.", encoding="utf-8")

            entry = index_entry(vault, page)
            link = wiki_link_for_path(vault, page, "MiniMind")

        self.assertIn("[[entities/MiniMind|MiniMind]]", entry)
        self.assertEqual(link, "[[entities/MiniMind|MiniMind]]")


if __name__ == "__main__":
    unittest.main()
