from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.connectors import ConnectorConfig, ConnectorRegistry, MarkdownConnector
from knoarbor.core.attachments import attachment_sidecar_path, write_attachment_sidecar


class MarkdownConnectorTests(unittest.TestCase):
    def test_discovers_markdown_files_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "a.md").write_text("# A\n", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "b.md").write_text("# B\n", encoding="utf-8")
            (nested / "ignored.txt").write_text("no", encoding="utf-8")

            refs = MarkdownConnector().discover(
                ConnectorConfig(settings={"roots": [str(root)], "recursive": True})
            )

        self.assertEqual([ref.display_name for ref in refs], ["a.md", "b.md"])
        self.assertTrue(all(ref.uri.startswith("file://") for ref in refs))
        self.assertTrue(all(ref.source_id.startswith("markdown:") for ref in refs))

    def test_fetch_and_to_document_preserve_content_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "note.md"
            path.write_text("# Note\n\nBody", encoding="utf-8")
            connector = MarkdownConnector()
            config = ConnectorConfig(settings={"roots": [str(path)]})
            ref = connector.discover(config)[0]
            raw = connector.fetch(ref, config)
            document = connector.to_document(raw, config)

        self.assertEqual(raw.content_type, "text/markdown")
        self.assertEqual(document.content.format, "markdown")
        self.assertEqual(document.content.text, "# Note\n\nBody")
        self.assertEqual(document.metadata["title"], "Note")
        self.assertEqual(document.fingerprint.content_hash, raw.content_hash)

    def test_to_document_collects_markdown_and_sidecar_attachments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            image_dir = root / "images"
            image_dir.mkdir()
            linked = image_dir / "linked.png"
            sidecar_only = image_dir / "sidecar.png"
            linked.write_bytes(b"linked")
            sidecar_only.write_bytes(b"sidecar")
            path = root / "paper.md"
            path.write_text("# Paper\n\n![diagram](images/linked.png)", encoding="utf-8")
            write_attachment_sidecar(
                path,
                [
                    {
                        "attachment_type": "image",
                        "name": "sidecar.png",
                        "path": str(sidecar_only),
                        "relative_path": "images/sidecar.png",
                        "description": "from sidecar",
                    }
                ],
                source="test",
            )
            connector = MarkdownConnector()
            config = ConnectorConfig(settings={"roots": [str(path)]})
            ref = connector.discover(config)[0]
            raw = connector.fetch(ref, config)
            document = connector.to_document(raw, config)

        self.assertEqual(document.metadata["attachment_count"], 2)
        self.assertEqual(
            sorted(item["relative_path"] for item in document.content.attachments),
            ["images/linked.png", "images/sidecar.png"],
        )

    def test_normalized_markdown_sidecar_uses_raw_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = (Path(tmp_dir) / "vault").resolve()
            markdown_path = vault / "raw" / "normalized" / "markdown" / "paper.md"
            markdown_path.parent.mkdir(parents=True)
            markdown_path.write_text("# Paper\n", encoding="utf-8")

            write_attachment_sidecar(markdown_path, [], source="test")

            self.assertEqual(
                attachment_sidecar_path(markdown_path),
                vault / "raw" / "sidecars" / "sources" / "paper.attachments.json",
            )
            self.assertTrue((vault / "raw" / "sidecars" / "sources" / "paper.attachments.json").exists())

    def test_registry_returns_markdown_connector(self) -> None:
        registry = ConnectorRegistry()

        self.assertIn("markdown", registry.names())
        self.assertIsInstance(registry.get("markdown"), MarkdownConnector)

    def test_missing_root_is_configuration_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Markdown root does not exist"):
            MarkdownConnector().discover(ConnectorConfig(settings={"roots": ["/missing/root"]}))


if __name__ == "__main__":
    unittest.main()
