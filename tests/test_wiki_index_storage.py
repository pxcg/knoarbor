from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.wiki_index import ensure_machine_index, index_entry, is_machine_index_stale, machine_index_dir, wiki_link_for_path


class WikiIndexStorageTests(unittest.TestCase):
    def test_update_index_catalogs_generated_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.write_text(
                "# Agent\n\n## Summary\n\nAgent loop notes.\n",
                encoding="utf-8",
            )

            VaultMaterializer().reconcile(vault, force=True)
            manifest = json.loads((machine_index_dir(vault) / "manifest.json").read_text(encoding="utf-8"))
            graph = json.loads((machine_index_dir(vault) / "graph_index.json").read_text(encoding="utf-8"))
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            search = json.loads((machine_index_dir(vault) / "search.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], "knoarbor_index.v1")
        self.assertGreaterEqual(manifest["page_count"], 1)
        self.assertEqual(graph["schema_version"], "knoarbor_graph_index.v1")
        self.assertEqual(pages["pages"][0]["path"], "Agent.md")
        self.assertEqual(search["entries"][0]["title"], "Agent")

    def test_machine_page_summary_preserves_full_summary_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            summary = (
                "A2A enables multiple AI agents to collaborate on complex tasks. "
                "It defines core components like Agent Card, Task, Message, Part, and Artifact, "
                "and supports three collaboration patterns: Master-Worker, Peer-to-Peer, and Hierarchical."
            )
            (vault / "wiki" / "pages" / "A2A.md").write_text(
                f"# A2A\n\n## Summary\n\n{summary}\n",
                encoding="utf-8",
            )

            VaultMaterializer().reconcile(vault, force=True)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            search = json.loads((machine_index_dir(vault) / "search.json").read_text(encoding="utf-8"))

        self.assertEqual(pages["pages"][0]["summary"], summary)
        self.assertIn("Hierarchical", search["entries"][0]["search_text"])
        self.assertNotIn("...", pages["pages"][0]["summary"])

    def test_machine_index_records_links_and_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "sources").mkdir(parents=True)
            (vault / "wiki" / "sources" / "Source.md").write_text("# Source\n", encoding="utf-8")
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "# Agent\n\n## Summary\n\nLinks to [[sources/Source|source]].\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n"
                "| C1 | raw/inbox/notes/agent.md | unit:0 | Agent notes. | high |\n",
                encoding="utf-8",
            )

            VaultMaterializer().reconcile(vault, force=True)
            links = json.loads((machine_index_dir(vault) / "links.json").read_text(encoding="utf-8"))
            sources = json.loads((machine_index_dir(vault) / "sources.json").read_text(encoding="utf-8"))

        self.assertEqual(links["links"][0]["target_path"], "sources/Source.md")
        self.assertEqual(sources["sources"][0]["source"], "raw/inbox/notes/agent.md")

    def test_graph_index_records_entities_relations_and_evidence_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
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

            VaultMaterializer().reconcile(vault, force=True)
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

    def test_graph_index_uses_wikilink_display_text_for_entity_rows_with_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "A2A.md").write_text(
                "# A2A\n\n"
                "## Entities\n\n"
                "- [[A2A]] (aliases: Agent-to-Agent)\n"
                "- [[concepts/Agent Card|Agent Card]] (aliases: 智能体名片)\n",
                encoding="utf-8",
            )

            VaultMaterializer().reconcile(vault, force=True)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            graph = json.loads((machine_index_dir(vault) / "graph_index.json").read_text(encoding="utf-8"))

        self.assertEqual(pages["pages"][0]["entities"], ["A2A", "Agent Card"])
        self.assertIn("A2A", {node["id"] for node in graph["nodes"]})
        self.assertIn("Agent Card", {node["id"] for node in graph["nodes"]})

    def test_graph_index_keeps_all_entity_rows_for_long_projection_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            entity_lines = "\n".join(f"- [[Entity {index:02d}]]" for index in range(1, 31))
            (vault / "wiki" / "pages" / "Long.md").write_text(
                f"# Long\n\n## Entities\n\n{entity_lines}\n",
                encoding="utf-8",
            )

            VaultMaterializer().reconcile(vault, force=True)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            graph = json.loads((machine_index_dir(vault) / "graph_index.json").read_text(encoding="utf-8"))

        self.assertEqual(len(pages["pages"][0]["entities"]), 30)
        self.assertIn("Entity 30", {node["id"] for node in graph["nodes"]})

    def test_machine_index_emits_page_identity_fields_for_unified_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nUnified page.\n\n## Claims\n\n- Agent loops coordinate tools.\n\n## Entities\n\n- Agent Loop\n- Tool Execution\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n## Summary\n\nCanonical unified page.\n",
                encoding="utf-8",
            )

            VaultMaterializer().reconcile(vault, force=True)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            records = {record["path"]: record for record in pages["pages"]}

        self.assertEqual(pages["schema_version"], "machine_pages.v2")
        self.assertEqual(records["Agent-Loop.md"]["schema_version"], "machine_page.v2")
        self.assertEqual(records["Agent-Loop.md"]["canonical_path"], "Agent-Loop.md")
        self.assertEqual(records["Agent-Loop.md"]["role"], "knowledge_page")
        self.assertEqual(records["OpenClaw.md"]["directory"], "pages")
        self.assertEqual(records["OpenClaw.md"]["canonical_path"], "OpenClaw.md")
        self.assertEqual(records["OpenClaw.md"]["role"], "knowledge_page")

    def test_update_index_keeps_runtime_views_virtual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            sources = vault / "wiki" / "sources"
            pages.mkdir(parents=True)
            sources.mkdir(parents=True)
            (pages / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop coordinates model and tool execution.\n",
                encoding="utf-8",
            )
            (sources / "Agent-Loop-Source.md").write_text(
                "# Agent Loop Source\n\n## Summary\n\nSource record for agent loop notes.\n",
                encoding="utf-8",
            )

            VaultMaterializer().reconcile(vault, force=True)
            pages_index = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            indexed_paths = {record["path"] for record in pages_index["pages"]}

        self.assertFalse((pages / "_views").exists())
        self.assertNotIn("_views/Home.md", indexed_paths)
        self.assertEqual(indexed_paths, {"Agent-Loop.md", "sources/Agent-Loop-Source.md"})

    def test_machine_index_stale_detection_refreshes_after_page_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text("# Agent\n", encoding="utf-8")

            VaultMaterializer().reconcile(vault, force=True)
            self.assertFalse(is_machine_index_stale(vault))
            (vault / "wiki" / "pages" / "Agent.md").write_text("# Agent\n\n## Summary\n\nUpdated.", encoding="utf-8")

            self.assertTrue(is_machine_index_stale(vault))
            self.assertFalse(ensure_machine_index(vault))
            VaultMaterializer().reconcile(vault, force=True)
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

            VaultMaterializer().reconcile(vault, force=True)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            indexed_paths = {record["path"] for record in pages["pages"]}

        self.assertFalse(any("lint_run_report" in path for path in indexed_paths))
        self.assertFalse(any(path.startswith("maintenance/") for path in indexed_paths))

    def test_index_entry_and_wikilink_use_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "MiniMind.md"
            page.write_text("# MiniMind\n\n## Summary\n\nA small model project.", encoding="utf-8")

            entry = index_entry(vault, page)
            link = wiki_link_for_path(vault, page, "MiniMind")

        self.assertIn("[[MiniMind|MiniMind]]", entry)
        self.assertEqual(link, "[[MiniMind|MiniMind]]")


if __name__ == "__main__":
    unittest.main()
