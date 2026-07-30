from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest
from knoarbor.services.chat_agent import ChatAgentService
from tests.helpers.chat_fakes import FakeChatClient, FakeServices, chat_answer_fixture


def _request(content: str, vault_path: str) -> ChatRequest:
    return ChatRequest(message=ChatMessageItem(role="user", content=content), vault_path=vault_path, append_ledger=False)


def _grounded(answer: str) -> dict[str, object]:
    return chat_answer_fixture(
        answer=answer.replace(" [1]", ""),
        spans=["sp_1_1"],
    )


class ChatMemoryTest(unittest.TestCase):
    def test_explicit_memory_is_written_after_chat(self) -> None:
        client = FakeChatClient(
            [
                _grounded("Agent Loop 是推理、行动和观察的循环 [1]。"),
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            response = service.chat(
                _request("请记住：后续默认用中文回答", tmp),
                FakeServices(),  # type: ignore[arg-type]
            )
            records_path = Path(tmp) / ".knoarbor" / "memory" / "records.jsonl"
            records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(response.memory_candidates), 1)
        self.assertEqual(len(response.memory_writes), 1)
        self.assertIn("默认用中文", response.memory_writes[0].content)
        self.assertEqual(records[0]["category"], "preference")

    def test_memory_context_reaches_decision_but_not_response_composer(self) -> None:
        client = FakeChatClient(
            [
                _grounded("Agent Loop 是推理、行动和观察的循环 [1]。"),
                _grounded("Agent Loop 是推理、行动和观察的循环 [1]。"),
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            first = service.chat(
                _request("请记住：后续默认用中文回答", tmp),
                FakeServices(),  # type: ignore[arg-type]
            )
            self.assertEqual(len(first.memory_writes), 1)
            service.chat(
                _request("Agent Loop 是什么？", tmp),
                FakeServices(),  # type: ignore[arg-type]
            )

        decision_request, composer_request = client.requests[-2:]
        decision_memory = [
            message
            for message in decision_request.messages
            if message.content.startswith("<knoarbor-memory-context>")
        ]
        composer_memory = [
            message
            for message in composer_request.messages
            if message.content.startswith("<knoarbor-memory-context>")
        ]
        self.assertEqual(len(decision_memory), 1)
        self.assertIn("默认用中文回答", decision_memory[0].content)
        self.assertEqual(composer_memory, [])


if __name__ == "__main__":
    unittest.main()
