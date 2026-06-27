from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.checkpoints import CheckpointStore


class CheckpointStoreTests(unittest.TestCase):
    def test_session_checkpoint_transitions_from_new_to_incremental_to_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            session_path = vault / "raw" / "chats" / "session_demo.json"
            session_path.parent.mkdir(parents=True)
            session_path.write_text(
                json.dumps(
                    {
                        "session_id": "demo",
                        "messages": [
                            {"role": "user", "content": "q1"},
                            {"role": "assistant", "content": "a1"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            store = CheckpointStore()
            state = store.read_state(vault / ".knoarbor" / "checkpoints" / "ingest_checkpoints.json")

            first = store.prepare_session_file(vault, state, session_path)
            pages = store.commit_session(
                vault,
                state,
                session_id=first.session_id,
                source_file=first.source_file,
                last_processed_raw_index=first.to_raw_index or 0,
                last_processed_content_hash=first.content_hash,
                generated_pages=["Demo.md"],
                connector_version="chat@1",
                parser_version="chat-parser@1",
            )
            second = store.prepare_session_file(vault, state, session_path)
            payload = json.loads(session_path.read_text(encoding="utf-8"))
            payload["messages"].append({"role": "user", "content": "q2"})
            session_path.write_text(json.dumps(payload), encoding="utf-8")
            third = store.prepare_session_file(vault, state, session_path)

        self.assertEqual(first.mode, "new_session")
        self.assertEqual(pages, ["Demo.md"])
        self.assertEqual(second.mode, "unchanged")
        self.assertFalse(second.should_process)
        self.assertEqual(third.mode, "incremental")
        self.assertEqual(third.from_raw_index, 2)

    def test_source_checkpoint_detects_changed_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            source_path = vault / "raw" / "notes" / "note.md"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("# Note\n", encoding="utf-8")
            store = CheckpointStore()
            state = store.read_state(vault / ".knoarbor" / "checkpoints" / "source_ingest_checkpoints.json")

            first = store.prepare_source_file(vault, state, source_path)
            store.commit_source(
                vault,
                state,
                source_id=first.source_id,
                source_file=first.source_file,
                content_hash=first.content_hash or "",
                generated_pages=[],
                connector_version="markdown@1",
                parser_version="markdown-parser@1",
            )
            source_path.write_text("# Note\n\nChanged\n", encoding="utf-8")
            second = store.prepare_source_file(vault, state, source_path)

        self.assertEqual(first.mode, "new_source")
        self.assertEqual(second.mode, "changed")
        self.assertTrue(second.should_process)

    def test_session_checkpoint_reprocesses_when_parser_version_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            session_path = vault / "raw" / "chats" / "session_demo.json"
            session_path.parent.mkdir(parents=True)
            payload = {
                "session_id": "demo",
                "messages": [
                    {"raw_index": 0, "role": "user", "content": "q1"},
                    {"raw_index": 1, "role": "assistant", "content": "a1"},
                ],
            }
            session_path.write_text(json.dumps(payload), encoding="utf-8")
            store = CheckpointStore()
            state = store.read_state(vault / ".knoarbor" / "checkpoints" / "ingest_checkpoints.json")

            first = store.prepare_session_payload(
                vault,
                state,
                session_path,
                payload,
                connector_version="chat@1",
                parser_version="chat-parser@1",
            )
            store.commit_session(
                vault,
                state,
                session_id=first.session_id,
                source_file=first.source_file,
                last_processed_raw_index=first.to_raw_index or 0,
                last_processed_content_hash=first.content_hash,
                generated_pages=["pages/Demo.md"],
                connector_version="chat@1",
                parser_version="chat-parser@1",
            )
            second = store.prepare_session_payload(
                vault,
                state,
                session_path,
                payload,
                connector_version="chat@1",
                parser_version="chat-parser@2",
            )

        self.assertTrue(second.should_process)
        self.assertEqual(second.mode, "changed_parser")
        self.assertIsNone(second.from_raw_index)
        self.assertEqual(second.to_raw_index, 1)

    def test_source_checkpoint_reprocesses_when_parser_version_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            source_path = vault / "raw" / "notes" / "note.md"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("# Note\n", encoding="utf-8")
            store = CheckpointStore()
            state = store.read_state(vault / ".knoarbor" / "checkpoints" / "source_ingest_checkpoints.json")

            first = store.prepare_source_file(
                vault,
                state,
                source_path,
                connector_version="markdown@1",
                parser_version="markdown-parser@1",
            )
            store.commit_source(
                vault,
                state,
                source_id=first.source_id,
                source_file=first.source_file,
                content_hash=first.content_hash or "",
                generated_pages=[],
                connector_version="markdown@1",
                parser_version="markdown-parser@1",
            )
            second = store.prepare_source_file(
                vault,
                state,
                source_path,
                connector_version="markdown@1",
                parser_version="markdown-parser@2",
            )

        self.assertTrue(second.should_process)
        self.assertEqual(second.mode, "changed_parser")


if __name__ == "__main__":
    unittest.main()
