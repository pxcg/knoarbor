from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.connectors import CodexConnector, ConnectorConfig, ConnectorRegistry
from knoarbor.pipelines.source import SourcePipeline


class CodexConnectorTests(unittest.TestCase):
    def test_discovers_jsonl_session_and_filters_process_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rollout-2026-05-24T10-00-00-demo.jsonl"
            _write_jsonl(
                path,
                [
                    {"type": "session_meta", "timestamp": "2026-05-24T10:00:00Z", "payload": {"id": "demo", "timestamp": "2026-05-24T10:00:00Z"}},
                    {
                        "type": "response_item",
                        "timestamp": "2026-05-24T10:00:01Z",
                        "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>\nnoise"}]},
                    },
                    {
                        "type": "response_item",
                        "timestamp": "2026-05-24T10:00:02Z",
                        "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "解释 Agent Loop"}]},
                    },
                    {
                        "type": "response_item",
                        "timestamp": "2026-05-24T10:00:03Z",
                        "payload": {"type": "function_call", "name": "terminal"},
                    },
                    {
                        "type": "response_item",
                        "timestamp": "2026-05-24T10:00:04Z",
                        "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Agent Loop 是感知、决策、行动、反馈的循环。"}]},
                    },
                ],
            )

            connector = CodexConnector()
            config = ConnectorConfig(settings={"session_files": [str(path)]})
            ref = connector.discover(config)[0]
            raw = connector.fetch(ref, config)
            document = connector.to_document(raw, config)
            payload = json.loads(document.content.text)

        self.assertEqual(ref.source_id, "codex:demo")
        self.assertEqual(ref.source_type, "codex_chat")
        self.assertEqual(raw.content_type, "application/x-jsonlines")
        self.assertEqual(document.source_type, "codex_chat")
        self.assertEqual(document.metadata["message_count"], 2)
        self.assertEqual(len(payload["turns"]), 2)
        self.assertEqual(payload["turns"][0]["raw_index"], 2)
        self.assertIn("Dropped", payload["prefilter_warnings"][0])

    def test_registry_and_source_pipeline_include_codex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rollout-demo.jsonl"
            _write_jsonl(path, [{"type": "session_meta", "payload": {"id": "demo"}}])

            registry = ConnectorRegistry()
            result = SourcePipeline(registry).run("codex", ConnectorConfig(settings={"session_files": [str(path)]}))

        self.assertIn("codex", registry.names())
        self.assertEqual(result.items[0].document.source_type, "codex_chat")

    def test_malformed_jsonl_line_is_reported_without_failing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rollout-demo.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "session_meta", "payload": {"id": "demo"}}, ensure_ascii=False),
                        '{"type": "response_item", "payload": ',
                        json.dumps(
                            {
                                "type": "response_item",
                                "payload": {
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": "保留这一轮"}],
                                },
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            connector = CodexConnector()
            config = ConnectorConfig(settings={"session_files": [str(path)]})
            ref = connector.discover(config)[0]
            raw = connector.fetch(ref, config)
            document = connector.to_document(raw, config)
            payload = json.loads(document.content.text)

        self.assertEqual(ref.source_id, "codex:demo")
        self.assertIn("parse_warnings", ref.metadata)
        self.assertEqual(len(payload["turns"]), 1)
        self.assertIn("Skipped malformed Codex JSONL line", payload["prefilter_warnings"][0])


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
