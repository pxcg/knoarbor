from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.connectors import ClaudeCodeConnector, ConnectorConfig, ConnectorRegistry
from knoarbor.core.checkpoints import CheckpointStore
from knoarbor.pipelines import SourcePipeline


class ClaudeCodeConnectorTests(unittest.TestCase):
    def test_discovers_jsonl_session_and_filters_runtime_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "6184bdcf-4789-4eea-9f5f-76b52330676a.jsonl"
            _write_jsonl(
                path,
                [
                    {"type": "permission-mode", "permissionMode": "default", "sessionId": "demo"},
                    {"type": "file-history-snapshot", "timestamp": "2026-05-26T10:00:00Z", "sessionId": "demo"},
                    {
                        "type": "user",
                        "timestamp": "2026-05-26T10:00:01Z",
                        "sessionId": "demo",
                        "cwd": "/tmp/workspace",
                        "message": {"role": "user", "content": "解释 Agent Loop"},
                    },
                    {
                        "type": "attachment",
                        "timestamp": "2026-05-26T10:00:02Z",
                        "sessionId": "demo",
                        "attachment": {"type": "skill_listing", "content": "noise"},
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-05-26T10:00:03Z",
                        "sessionId": "demo",
                        "message": {
                            "role": "assistant",
                            "model": "deepseek-v4-pro",
                            "content": [{"type": "thinking", "thinking": "hidden reasoning"}],
                        },
                    },
                    {
                        "type": "assistant",
                        "timestamp": "2026-05-26T10:00:04Z",
                        "sessionId": "demo",
                        "version": "2.1.142",
                        "message": {
                            "role": "assistant",
                            "model": "deepseek-v4-pro",
                            "content": [{"type": "text", "text": "Agent Loop 是思考、行动、观察的循环。"}],
                        },
                    },
                    {
                        "type": "user",
                        "timestamp": "2026-05-26T10:00:05Z",
                        "sessionId": "demo",
                        "message": {"role": "user", "content": [{"type": "tool_result", "content": "tool output"}]},
                    },
                    {"type": "ai-title", "aiTitle": "Agent Loop explanation", "sessionId": "demo"},
                ],
            )

            connector = ClaudeCodeConnector()
            config = ConnectorConfig(settings={"session_files": [str(path)]})
            ref = connector.discover(config)[0]
            raw = connector.fetch(ref, config)
            document = connector.to_document(raw, config)
            payload = json.loads(document.content.text)

        self.assertEqual(ref.source_id, "claude_code:demo")
        self.assertEqual(ref.source_type, "claude_code_chat")
        self.assertEqual(raw.content_type, "application/x-jsonlines")
        self.assertEqual(document.source_type, "claude_code_chat")
        self.assertEqual(document.metadata["message_count"], 2)
        self.assertEqual(document.metadata["model"], "deepseek-v4-pro")
        self.assertEqual(len(payload["turns"]), 2)
        self.assertEqual(payload["turns"][0]["raw_index"], 2)
        self.assertNotIn("hidden reasoning", document.content.text)
        self.assertNotIn("tool output", document.content.text)
        self.assertIn("Dropped", payload["prefilter_warnings"][0])

    def test_registry_and_source_pipeline_include_claude_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "demo.jsonl"
            _write_jsonl(path, [{"type": "permission-mode", "sessionId": "demo"}])

            registry = ConnectorRegistry()
            result = SourcePipeline(registry).run("claude_code", ConnectorConfig(settings={"session_files": [str(path)]}))

        self.assertIn("claude_code", registry.names())
        self.assertEqual(result.items[0].document.source_type, "claude_code_chat")

    def test_checkpoint_payload_uses_claude_code_turn_raw_indexes(self) -> None:
        payload = {
            "session_id": "demo",
            "turns": [
                {"raw_index": 4, "role": "user", "content": "q1"},
                {"raw_index": 9, "role": "assistant", "content": "a1"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            source_path = vault / "raw" / "chats" / "demo.jsonl"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("{}", encoding="utf-8")
            store = CheckpointStore()
            state = {"sessions": {}, "sources": {}}
            plan = store.prepare_session_payload(vault, state, source_path, payload)

        self.assertEqual(plan.mode, "new_session")
        self.assertEqual(plan.to_raw_index, 9)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
