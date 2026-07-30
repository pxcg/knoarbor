from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.connectors import ConnectorConfig, ConnectorRegistry, OpenClawConnector
from knoarbor.pipelines.source import SourcePipeline


class OpenClawConnectorTests(unittest.TestCase):
    def test_discovers_main_jsonl_session_and_filters_runtime_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "467d3a5e-1bac-42c5-86b4-748365c6791e.jsonl"
            trajectory = root / "467d3a5e-1bac-42c5-86b4-748365c6791e.trajectory.jsonl"
            _write_jsonl(
                path,
                [
                    {"type": "session", "id": "demo", "timestamp": "2026-05-24T10:00:00Z", "cwd": "/tmp/workspace"},
                    {"type": "model_change", "provider": "deepseek", "modelId": "deepseek-v4-flash", "timestamp": "2026-05-24T10:00:00Z"},
                    {
                        "type": "message",
                        "timestamp": "2026-05-24T10:00:01Z",
                        "message": {"role": "user", "content": [{"type": "text", "text": "<environment_context>\nnoise"}]},
                    },
                    {
                        "type": "message",
                        "timestamp": "2026-05-24T10:00:02Z",
                        "message": {"role": "user", "content": [{"type": "text", "text": "解释 OpenClaw 的记忆设计"}]},
                    },
                    {
                        "type": "message",
                        "timestamp": "2026-05-24T10:00:03Z",
                        "message": {
                            "role": "assistant",
                            "provider": "deepseek",
                            "model": "deepseek-v4-flash",
                            "content": [
                                {"type": "thinking", "thinking": "hidden reasoning"},
                                {"type": "text", "text": "OpenClaw 使用工作区文件作为长期记忆。"},
                                {"type": "toolCall", "name": "write", "arguments": {"path": "MEMORY.md"}},
                            ],
                        },
                    },
                    {
                        "type": "message",
                        "timestamp": "2026-05-24T10:00:04Z",
                        "message": {"role": "toolResult", "content": [{"type": "text", "text": "tool output"}]},
                    },
                ],
            )
            trajectory.write_text("{}", encoding="utf-8")

            connector = OpenClawConnector()
            config = ConnectorConfig(settings={"sessions_dir": str(root)})
            refs = connector.discover(config)
            raw = connector.fetch(refs[0], config)
            document = connector.to_document(raw, config)
            payload = json.loads(document.content.text)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].source_id, "openclaw:demo")
        self.assertEqual(refs[0].source_type, "openclaw_chat")
        self.assertEqual(raw.content_type, "application/x-jsonlines")
        self.assertEqual(document.source_type, "openclaw_chat")
        self.assertEqual(document.metadata["message_count"], 2)
        self.assertEqual(document.metadata["provider"], "deepseek")
        self.assertEqual(document.metadata["model"], "deepseek-v4-flash")
        self.assertEqual(len(payload["turns"]), 2)
        self.assertEqual(payload["turns"][0]["raw_index"], 3)
        self.assertNotIn("hidden reasoning", document.content.text)
        self.assertNotIn("tool output", document.content.text)
        self.assertIn("Dropped", payload["prefilter_warnings"][0])

    def test_registry_and_source_pipeline_include_openclaw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "demo.jsonl"
            _write_jsonl(path, [{"type": "session", "id": "demo"}])

            registry = ConnectorRegistry()
            result = SourcePipeline(registry).run("openclaw", ConnectorConfig(settings={"session_files": [str(path)]}))

        self.assertIn("openclaw", registry.names())
        self.assertEqual(result.items[0].document.source_type, "openclaw_chat")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
