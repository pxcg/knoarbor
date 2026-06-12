from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from knoarbor.core.config import MemoryConfig
from knoarbor.core.schemas.chat import ChatMessageItem
from knoarbor.services.memory import MemoryService


class MemoryServiceTest(unittest.TestCase):
    def test_explicit_low_risk_memory_writes_record_candidate_and_events(self) -> None:
        service = MemoryService()
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            candidates, writes = service.capture_explicit_memory(
                vault_path=vault,
                vault_id="default",
                messages=[ChatMessageItem(role="user", content="以后默认用中文回答")],
                config=MemoryConfig(enabled=True, auto_write_explicit_low_risk=True),
                chat_id="chat_test",
            )
            records = _read_jsonl(vault / ".knoarbor/memory/records.jsonl")
            candidate_records = _read_jsonl(vault / ".knoarbor/memory/candidates.jsonl")
            events = _read_jsonl(vault / ".knoarbor/memory/events.jsonl")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(writes), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(candidate_records[0]["status"], "written")
        self.assertEqual([event["event_type"] for event in events], ["candidate_created", "written"])

    def test_candidate_review_when_auto_write_disabled(self) -> None:
        service = MemoryService()
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            candidates, writes = service.capture_explicit_memory(
                vault_path=vault,
                vault_id="default",
                messages=[ChatMessageItem(role="user", content="remember: answer briefly")],
                config=MemoryConfig(enabled=True, auto_write_explicit_low_risk=False),
                chat_id="chat_test",
            )
            records_path = vault / ".knoarbor/memory/records.jsonl"

        self.assertEqual(candidates[0].status, "pending")
        self.assertEqual(writes, [])
        self.assertFalse(records_path.exists())

    def test_recall_returns_fenced_context(self) -> None:
        service = MemoryService()
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            service.capture_explicit_memory(
                vault_path=vault,
                vault_id="default",
                messages=[ChatMessageItem(role="user", content="请记住：回答时先给结论")],
                config=MemoryConfig(enabled=True),
                chat_id="chat_test",
            )
            recall = service.recall(vault_path=vault, vault_id="default", query="RAG 怎么设计？", config=MemoryConfig(enabled=True), chat_id="chat_next")

        self.assertEqual(len(recall.records), 1)
        self.assertIn("<knoarbor-memory-context>", recall.context_block)
        self.assertIn("先给结论", recall.context_block)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    unittest.main()
