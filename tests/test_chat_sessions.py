from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from knoarbor.core.schemas.chat import ChatCitation, ChatMessageItem, ChatRequest, ChatResponse
from knoarbor.services.chat_agent import ChatAgentService
from knoarbor.services.chat_sessions import ChatSessionStore
from tests.helpers.chat_fakes import FakeChatClient, FakeServices


class ChatSessionTest(unittest.TestCase):
    def test_chat_appends_token_ledger_records(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "Agent Loop 是推理、行动和观察的循环。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            response = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop")], vault_path=tmp),
                FakeServices(),  # type: ignore[arg-type]
            )
            ledger = Path(tmp) / ".knoarbor" / "ledgers" / "token.jsonl"
            records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(response.stats["model_calls"], 2)
        self.assertEqual(records[0]["flow"], "chat")
        self.assertEqual(records[0]["agent"], "wiki_chat_agent")
        self.assertIn("Agent-Loop.md", records[0]["page_paths"])
        self.assertIn("sources/Agent-Loop-Source.md", records[0]["page_paths"])

    def test_chat_persists_session_and_can_continue(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "第一轮回答。", "citations": []},
                {"answer": "第二轮回答。", "citations": []},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="第一轮问题")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            self.assertTrue(first.session_id)
            record = services.chat_sessions.read_session(tmp, first.session_id or "")
            self.assertEqual([message.content for message in record.messages], ["第一轮问题", "第一轮回答。"])

            second = service.chat(
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="第二轮问题")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            record = services.chat_sessions.read_session(tmp, second.session_id or "")

        self.assertEqual(first.session_id, second.session_id)
        self.assertEqual([message.content for message in record.messages], ["第一轮问题", "第一轮回答。", "第二轮问题", "第二轮回答。"])
        self.assertEqual(len(record.turns), 2)
        self.assertEqual(record.turns[0].user_message.content, "第一轮问题")
        self.assertEqual(record.turns[0].assistant_message.content, "第一轮回答。")
        self.assertEqual(record.turns[1].user_message.content, "第二轮问题")
        self.assertEqual(record.turns[1].assistant_message.content, "第二轮回答。")
        second_model_messages = client.requests[-1].messages
        second_answer_state = json.loads(second_model_messages[-1].content)["answer_state"]
        self.assertEqual(second_answer_state["latest_user_message"], "第二轮问题")
        self.assertEqual(second_answer_state["conversation_context"][0]["assistant_answer"], "第一轮回答。")

    def test_retry_latest_turn_replaces_answer_without_duplicating_user_message(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "第一版回答。", "citations": []},
                {"answer": "重新生成的回答。", "citations": []},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            previous, retry_user_message = services.chat_sessions.prepare_retry_latest_turn(tmp, first.session_id or "")
            self.assertEqual(retry_user_message.content, "Agent Loop 是什么？")
            trimmed = services.chat_sessions.read_session(tmp, first.session_id or "")
            self.assertEqual(trimmed.messages, [])
            self.assertEqual(trimmed.turns, [])

            retry = service.chat(
                ChatRequest(session_id=first.session_id, messages=[retry_user_message], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            record = services.chat_sessions.read_session(tmp, retry.session_id or "")

        self.assertEqual(previous.messages[-1].content, "第一版回答。")
        self.assertEqual([message.content for message in record.messages], ["Agent Loop 是什么？", "重新生成的回答。"])
        self.assertEqual(len(record.turns), 1)
        self.assertEqual(record.turns[0].assistant_message.content, "重新生成的回答。")

    def test_session_turns_keep_per_answer_citations(self) -> None:
        store = ChatSessionStore()
        with tempfile.TemporaryDirectory() as tmp:
            first = ChatResponse(
                session_id="chat_test1234",
                answer="第一轮回答。",
                messages=[
                    ChatMessageItem(role="user", content="第一轮问题"),
                    ChatMessageItem(role="assistant", content="第一轮回答。"),
                ],
                citations=[ChatCitation(kind="page", path="First.md", title="First")],
            )
            second = ChatResponse(
                session_id="chat_test1234",
                answer="第二轮回答。",
                messages=[
                    ChatMessageItem(role="user", content="第一轮问题"),
                    ChatMessageItem(role="assistant", content="第一轮回答。"),
                    ChatMessageItem(role="user", content="第二轮问题"),
                    ChatMessageItem(role="assistant", content="第二轮回答。"),
                ],
                citations=[ChatCitation(kind="page", path="Second.md", title="Second")],
            )
            store.persist_response(tmp, response=first, request_messages=first.messages, vault_id="test", vault_name="Test")
            record = store.persist_response(tmp, response=second, request_messages=second.messages, vault_id="test", vault_name="Test")

        self.assertEqual(len(record.turns), 2)
        self.assertEqual(record.turns[0].citations[0].path, "First.md")
        self.assertEqual(record.turns[1].citations[0].path, "Second.md")
        self.assertEqual(record.citations[0].path, "Second.md")

    def test_session_title_can_be_updated(self) -> None:
        store = ChatSessionStore()
        with tempfile.TemporaryDirectory() as tmp:
            response = ChatResponse(
                session_id="chat_title1234",
                answer="回答。",
                messages=[
                    ChatMessageItem(role="user", content="原始问题"),
                    ChatMessageItem(role="assistant", content="回答。"),
                ],
            )
            store.persist_response(tmp, response=response, request_messages=response.messages, vault_id="test", vault_name="Test")
            updated = store.update_title(tmp, "chat_title1234", "  新标题  ")
            reread = store.read_session(tmp, "chat_title1234")

        self.assertEqual(updated.title, "新标题")
        self.assertEqual(reread.title, "新标题")
        self.assertEqual(reread.messages[0].content, "原始问题")

    def test_chat_session_can_be_used_as_ingest_source_document(self) -> None:
        client = FakeChatClient([{"answer": "这是回答。", "citations": []}])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            response = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="请解释 KnoArbor chat。")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            source_document = services.chat_sessions.to_source_document(tmp, response.session_id or "")

        self.assertEqual(source_document.source_type, "knoarbor_chat")
        self.assertEqual(source_document.origin.connector, "knoarbor_chat")
        self.assertEqual(source_document.metadata["source_app"], "knoarbor")
        self.assertEqual(source_document.content.format, "json")
        self.assertEqual(source_document.content.sections[0]["raw_index"], 0)
        self.assertIn("knoarbor_chat_extract.v1", source_document.content.text)

    def test_chat_session_close_and_ingest_metadata_are_recorded(self) -> None:
        client = FakeChatClient([{"answer": "这是回答。", "citations": []}])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            response = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="请解释归档。")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            closed = services.chat_sessions.close_session(tmp, response.session_id or "")
            updated = services.chat_sessions.mark_ingest_started(tmp, response.session_id or "", "20260615_test")

        self.assertEqual(closed.status, "closed")
        self.assertIsNotNone(closed.closed_at)
        self.assertIsNotNone(closed.ingest_candidate)
        self.assertFalse(closed.ingest_candidate.should_ingest)
        self.assertEqual(updated.last_ingest_run_id, "20260615_test")
        self.assertIsNotNone(updated.last_ingested_at)


if __name__ == "__main__":
    unittest.main()
