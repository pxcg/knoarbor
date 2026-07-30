from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.connectors import ConnectorConfig
from knoarbor.core.config import KnoArborConfig
from knoarbor.pipelines.source import SourcePipeline


class SourcePipelineTests(unittest.TestCase):
    def test_pipeline_normalizes_markdown_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agent.md").write_text("# Agent\n\nLoop notes.", encoding="utf-8")

            result = SourcePipeline().run(
                "markdown",
                ConnectorConfig(settings={"roots": [str(root)]}),
            )

        self.assertEqual(result.connector, "markdown")
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.ref.display_name, "agent.md")
        self.assertEqual(item.raw.content_type, "text/markdown")
        self.assertEqual(item.document.metadata["title"], "Agent")
        self.assertEqual(item.document.content.text, "# Agent\n\nLoop notes.")

    def test_pipeline_rejects_unknown_connector(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown connector"):
            SourcePipeline().run("missing", ConnectorConfig())

    def test_pipeline_normalizes_processed_document_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            markdown = root / "markdown"
            markdown.mkdir()
            (markdown / "paper.md").write_text("# Parsed Paper\n\nMinerU output.", encoding="utf-8")

            result = SourcePipeline().run(
                "markdown",
                ConnectorConfig(settings={"roots": [str(markdown)]}),
            )

        self.assertEqual(result.connector, "markdown")
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.document.content.format, "markdown")
        self.assertEqual(item.document.metadata["title"], "Parsed Paper")

    def test_pipeline_runs_enabled_connectors_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            markdown = root / "notes"
            markdown.mkdir()
            (markdown / "note.md").write_text("# Note\n\nBody.", encoding="utf-8")
            config = KnoArborConfig.model_validate(
                {
                    "vault": {"path": str(root)},
                    "connectors": {
                        "markdown": {"enabled": True, "settings": {"roots": [str(markdown)]}},
                        "hermes": {"enabled": False, "settings": {}},
                    },
                }
            )

            result = SourcePipeline().run_enabled(config)

        self.assertEqual(result.stats["connector_count"], 1)
        self.assertEqual(result.stats["item_count"], 1)
        self.assertEqual(result.results[0].connector, "markdown")


if __name__ == "__main__":
    unittest.main()
