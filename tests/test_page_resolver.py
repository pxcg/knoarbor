import unittest
from pathlib import Path
import tempfile

from knoarbor.retrieval.page_resolver import page_resolver_conflicts, resolve_page_reference
from knoarbor.retrieval.wiki_links import resolve_wikilink_target
from knoarbor.services.wiki_pages import WikiPageService
from knoarbor.storage import update_index


class PageResolverTests(unittest.TestCase):
    def test_resolves_canonical_legacy_title_and_wikilink_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "pages"
            pages_root.mkdir()
            (pages_root / "OpenClaw.md").write_text(
                "---\npage_kind: entity\nlegacy_paths: entities/OpenClaw.md\n---\n"
                "# OpenClaw\n\n## Summary\n\nAgent platform.\n",
                encoding="utf-8",
            )
            update_index(vault)

            by_path = resolve_page_reference(vault, "OpenClaw.md")
            by_title = resolve_page_reference(vault, "OpenClaw")
            by_legacy = resolve_page_reference(vault, "entities/OpenClaw.md")
            by_link = resolve_wikilink_target(vault, "[[entities/OpenClaw|OpenClaw]]")

        self.assertTrue(by_path.resolved)
        self.assertEqual(by_path.resolved_path, "OpenClaw.md")
        self.assertEqual(by_path.canonical_path, "OpenClaw.md")
        self.assertEqual(by_path.page_kind, "entity")
        self.assertEqual(by_title.resolved_path, "OpenClaw.md")
        self.assertEqual(by_legacy.resolved_path, "OpenClaw.md")
        self.assertEqual(by_link, "OpenClaw.md")

    def test_reports_ambiguous_title_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "pages"
            pages_root.mkdir()
            (pages_root / "Agent-Loop.md").write_text("# Agent Loop\n", encoding="utf-8")
            concepts = pages_root / "concepts"
            concepts.mkdir()
            (concepts / "Agent-Loop.md").write_text("# Agent Loop\n", encoding="utf-8")
            update_index(vault)

            resolution = resolve_page_reference(vault, "Agent Loop")
            conflicts = page_resolver_conflicts(vault)

        self.assertEqual(resolution.status, "ambiguous")
        self.assertEqual(resolution.conflicts, ["Agent-Loop.md", "concepts/Agent-Loop.md"])
        self.assertTrue(any(conflict["key"] == "agent-loop" for conflict in conflicts))

    def test_wiki_page_service_reads_page_through_legacy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "pages"
            pages_root.mkdir()
            (pages_root / "OpenClaw.md").write_text(
                "---\npage_kind: entity\nlegacy_paths: entities/OpenClaw.md\n---\n"
                "# OpenClaw\n\n## Summary\n\nAgent platform.\n",
                encoding="utf-8",
            )
            update_index(vault)

            detail = WikiPageService().read_page(vault, "entities/OpenClaw.md")

        self.assertEqual(detail.path, "OpenClaw.md")
        self.assertEqual(detail.canonical_path, "OpenClaw.md")
        self.assertEqual(detail.legacy_paths, ["entities/OpenClaw.md"])
        self.assertIn("# OpenClaw", detail.content)


if __name__ == "__main__":
    unittest.main()
