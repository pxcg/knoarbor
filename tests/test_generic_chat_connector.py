from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.connectors.generic_chat import GenericChatConnector


class GenericChatConnectorTests(unittest.TestCase):
    def test_jsonl_chat_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "chat.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"role": "user", "content": "What is KnoArbor?", "timestamp": "2026-01-01T00:00:00"}),
                        json.dumps({"role": "assistant", "content": "A wiki engine.", "timestamp": "2026-01-01T00:00:01"}),
                    ]
                ),
                encoding="utf-8",
            )
            connector = GenericChatConnector()
            config = ConnectorConfig(enabled=True, settings={"roots": [tmp_dir]})

            refs = connector.discover(config)
            raw = connector.fetch(refs[0], config)
            document = connector.to_document(raw, config)

        self.assertEqual(refs[0].source_type, "generic_chat")
        self.assertEqual(document.source_type, "generic_chat")
        self.assertEqual(document.metadata["message_count"], 2)
        self.assertIn("What is KnoArbor?", document.content.text)

    def test_sqlite_chat_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "chat.sqlite"
            connection = sqlite3.connect(path)
            try:
                connection.execute("create table messages (id integer primary key, role text, content text, created_at text)")
                connection.execute("insert into messages(role, content, created_at) values (?, ?, ?)", ("user", "hello", "1"))
                connection.execute("insert into messages(role, content, created_at) values (?, ?, ?)", ("assistant", "hi", "2"))
                connection.commit()
            finally:
                connection.close()
            connector = GenericChatConnector()
            config = ConnectorConfig(enabled=True, settings={"roots": [tmp_dir], "patterns": ["*.sqlite"]})

            refs = connector.discover(config)
            raw = connector.fetch(refs[0], config)
            document = connector.to_document(raw, config)

        self.assertEqual(document.source_type, "generic_chat")
        self.assertEqual(document.metadata["message_count"], 2)
        self.assertIn("hello", document.content.text)


if __name__ == "__main__":
    unittest.main()
