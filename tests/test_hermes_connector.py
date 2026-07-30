from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.connectors import ConnectorConfig, ConnectorRegistry, HermesConnector
from knoarbor.pipelines.source import SourcePipeline


class HermesConnectorTests(unittest.TestCase):
    def test_discovers_session_files_and_preserves_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            session = root / "session_20260517_demo.json"
            session.write_text(
                json.dumps(
                    {
                        "session_id": "20260517_demo",
                        "platform": "cli",
                        "model": "deepseek",
                        "session_start": "2026-05-17T10:00:00",
                        "last_updated": "2026-05-17T10:01:00",
                        "messages": [{"role": "user", "content": "hello"}],
                    }
                ),
                encoding="utf-8",
            )

            refs = HermesConnector().discover(ConnectorConfig(settings={"sessions_dir": str(root)}))

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].source_id, "hermes:20260517_demo")
        self.assertEqual(refs[0].source_type, "hermes_chat")
        self.assertEqual(refs[0].metadata["message_count"], 1)

    def test_fetch_and_to_document_returns_json_source_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "session_demo.json"
            path.write_text(
                json.dumps(
                    {
                        "session_id": "demo",
                        "platform": "cli",
                        "messages": [{"role": "assistant", "content": "answer"}],
                    }
                ),
                encoding="utf-8",
            )
            connector = HermesConnector()
            config = ConnectorConfig(settings={"session_files": [str(path)]})
            ref = connector.discover(config)[0]
            raw = connector.fetch(ref, config)
            document = connector.to_document(raw, config)

        self.assertEqual(raw.content_type, "application/json")
        self.assertEqual(document.content.format, "json")
        self.assertEqual(document.metadata["session_id"], "demo")
        self.assertEqual(document.metadata["message_count"], 1)
        self.assertEqual(document.fingerprint.content_hash, raw.content_hash)

    def test_registry_and_source_pipeline_include_hermes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "session_demo.json"
            path.write_text(json.dumps({"session_id": "demo", "messages": []}), encoding="utf-8")

            registry = ConnectorRegistry()
            result = SourcePipeline(registry).run(
                "hermes",
                ConnectorConfig(settings={"session_files": [str(path)]}),
            )

        self.assertIn("hermes", registry.names())
        self.assertEqual(result.items[0].document.source_type, "hermes_chat")

    def test_missing_sessions_dir_is_configuration_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Hermes sessions directory does not exist"):
            HermesConnector().discover(ConnectorConfig(settings={"sessions_dir": "/missing/hermes"}))


if __name__ == "__main__":
    unittest.main()
