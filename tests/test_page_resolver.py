import unittest
from pathlib import Path
import tempfile

from knoarbor.retrieval.page_resolver import page_resolver_conflicts, resolve_page_reference
from knoarbor.services.wiki_pages import WikiPageService
from knoarbor.storage.materialization import VaultMaterializer


class PageResolverTests(unittest.TestCase):
    def test_resolves_path_title_and_wikilink_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "wiki" / "pages"
            pages_root.mkdir(parents=True)
            (pages_root / "OpenClaw.md").write_text(
                "---\n---\n"
                "# OpenClaw\n\n## Summary\n\nAgent platform.\n",
                encoding="utf-8",
            )
            VaultMaterializer().reconcile(vault, force=True)

            by_path = resolve_page_reference(vault, "OpenClaw.md")
            by_title = resolve_page_reference(vault, "OpenClaw")
            by_link = resolve_page_reference(vault, "[[OpenClaw|OpenClaw]]")

        self.assertTrue(by_path.resolved)
        self.assertEqual(by_path.resolved_path, "OpenClaw.md")
        self.assertEqual(by_path.canonical_path, "OpenClaw.md")
        self.assertEqual(by_title.resolved_path, "OpenClaw.md")
        self.assertEqual(by_link.resolved_path, "OpenClaw.md")

    def test_reports_ambiguous_title_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "wiki" / "pages"
            pages_root.mkdir(parents=True)
            (pages_root / "Agent-Loop.md").write_text("# Agent Loop\n", encoding="utf-8")
            (pages_root / "Agent-Loop-Duplicate.md").write_text("# Agent Loop\n", encoding="utf-8")
            VaultMaterializer().reconcile(vault, force=True)

            resolution = resolve_page_reference(vault, "Agent Loop")
            conflicts = page_resolver_conflicts(vault)

        self.assertEqual(resolution.status, "ambiguous")
        self.assertEqual(resolution.conflicts, ["Agent-Loop-Duplicate.md", "Agent-Loop.md"])
        self.assertTrue(any(conflict["key"] == "agent-loop" for conflict in conflicts))

    def test_wiki_page_service_reads_page_through_current_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "wiki" / "pages"
            pages_root.mkdir(parents=True)
            (pages_root / "OpenClaw.md").write_text(
                "---\n---\n"
                "# OpenClaw\n\n## Summary\n\nAgent platform.\n",
                encoding="utf-8",
            )
            VaultMaterializer().reconcile(vault, force=True)

            detail = WikiPageService().read_page(vault, "OpenClaw.md")

        self.assertEqual(detail.path, "OpenClaw.md")
        self.assertEqual(detail.canonical_path, "OpenClaw.md")
        self.assertIn("# OpenClaw", detail.content)


if __name__ == "__main__":
    unittest.main()
