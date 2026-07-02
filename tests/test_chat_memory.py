from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest
from knoarbor.services.chat_agent import ChatAgentService
from tests.helpers.chat_fakes import FakeChatClient, FakeServices


class ChatMemoryTest(unittest.TestCase):
    def test_explicit_memory_is_written_after_chat(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "我会按你的偏好处理后续回答。",
                    "citations": [],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            response = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="请记住：后续默认用中文回答")], vault_path=tmp, append_ledger=False),
                FakeServices(),  # type: ignore[arg-type]
            )
            records_path = Path(tmp) / ".knoarbor" / "memory" / "records.jsonl"
            records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(response.memory_candidates), 1)
        self.assertEqual(len(response.memory_writes), 1)
        self.assertIn("默认用中文", response.memory_writes[0].content)
        self.assertEqual(records[0]["category"], "preference")

    def test_memory_context_is_injected_before_user_message(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "我会用中文回答。",
                    "citations": [],
                },
                {
                    "answer": "Agent Loop 是推理、行动和观察的循环。",
                    "citations": [],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            first = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="请记住：后续默认用中文回答")], vault_path=tmp, append_ledger=False),
                FakeServices(),  # type: ignore[arg-type]
            )
            self.assertEqual(len(first.memory_writes), 1)
            service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_path=tmp, append_ledger=False),
                FakeServices(),  # type: ignore[arg-type]
            )

        second_request = client.requests[-1]
        memory_messages = [message for message in second_request.messages if message.content.startswith("<knoarbor-memory-context>")]
        self.assertEqual(len(memory_messages), 1)
        self.assertIn("默认用中文回答", memory_messages[0].content)


if __name__ == "__main__":
    unittest.main()
