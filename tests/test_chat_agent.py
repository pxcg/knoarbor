from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest
from knoarbor.core.errors import ModelOutputError
from knoarbor.core.schemas.wiki_query import WikiAnswerScope, WikiAnswerSet, WikiEvidenceCoverage, WikiSearchResponse, WikiSearchResult
from knoarbor.semantic.llm import ChatCompletionRequest, ChatCompletionResponse
from knoarbor.services.chat_agent import ChatAgentService
from knoarbor.services.chat_sessions import ChatSessionStore
from knoarbor.services.memory import MemoryService


class FakeChatClient:
    model = "fake-model"

    def __init__(self, outputs: list[dict[str, object]], *, provider: str = "fake") -> None:
        self.provider = provider
        self.outputs = list(outputs)
        self.requests: list[ChatCompletionRequest] = []

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self.requests.append(request)
        if not self.outputs:
            raise AssertionError("No fake model output left")
        payload = self.outputs.pop(0)
        if isinstance(payload, str):
            content = payload
        else:
            content = json.dumps(payload, ensure_ascii=False)
        return ChatCompletionResponse(
            content=content,
            provider=self.provider,
            model=self.model,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )


class FakeWikiSearch:
    def __init__(self) -> None:
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return WikiSearchResponse(
            query=request.query,
            retrieval_mode=request.mode,
            results=[
                WikiSearchResult(
                    path="sources/Agent-Loop-Source.md",
                    title="Agent Loop Source",
                    type="source",
                    role="source",
                    status="draft",
                    score=12.0,
                    relevance="high",
                    match_kind="direct",
                    reason="source digest match",
                    summary="Source digest for agent loop notes.",
                    content="Source digest content.",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                ),
                WikiSearchResult(
                    path="concepts/Agent-Loop.md",
                    title="Agent Loop",
                    type="concept",
                    role="primary",
                    status="draft",
                    score=9.0,
                    relevance="high",
                    match_kind="direct",
                    reason="title match",
                    summary="Agent loop alternates reasoning, action, and observation.",
                    key_points=["Use the maintained page as the main answer unit."],
                    content="Agent Loop full maintained page content.",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                ),
                WikiSearchResult(
                    path="concepts/Session-Memory-Architecture-for-Agent-Loops.md",
                    title="Session Memory Architecture for Agent Loops",
                    type="concept",
                    role="supporting",
                    status="draft",
                    score=7.0,
                    relevance="medium",
                    match_kind="related",
                    reason="related implementation page",
                    summary="Session memory explains production support for agent loops.",
                    key_points=["Memory recall and compaction support long-running agent loops."],
                    content="Session memory supporting page content for production agent loops.",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                )
            ],
            primary_pages=[],
            supporting_pages=[],
            source_pages=[],
            answer_scope=WikiAnswerScope(kind="broad", vault_ids=["agent-engineering"], reason="test"),
            answer_set=WikiAnswerSet(
                kind="multi_page",
                primary_paths=["concepts/Agent-Loop.md"],
                supporting_paths=["concepts/Session-Memory-Architecture-for-Agent-Loops.md"],
                source_paths=["sources/Agent-Loop-Source.md"],
            ),
            evidence_coverage=WikiEvidenceCoverage(status="strong", primary_count=1, supporting_count=1, source_count=1),
            context_pack="Agent Loop context",
            answer_guidance=[],
            warnings=[],
        )


@dataclass
class FakeServices:
    wiki_search: FakeWikiSearch = field(default_factory=FakeWikiSearch)
    memory: MemoryService = field(default_factory=MemoryService)
    chat_sessions: ChatSessionStore = field(default_factory=ChatSessionStore)


class ChatAgentServiceTest(unittest.TestCase):
    def test_search_tool_then_final_answer(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "Agent Loop"}},
                {
                    "type": "final",
                    "answer": "Agent Loop 是推理、行动和观察的循环。",
                    "citations": [{"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        services = FakeServices()
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertIn("Agent Loop", response.answer)
        self.assertEqual(len(response.tool_trace), 1)
        self.assertEqual(response.tool_trace[0].tool, "search_wiki")
        self.assertEqual(response.stats["model_calls"], 2)
        self.assertEqual(response.stats["tool_calls"], 1)
        self.assertEqual(response.stats["total_tokens"], 30)
        self.assertEqual(response.citations[0].path, "concepts/Agent-Loop.md")
        evidence_pack = response.tool_trace[0].result["evidence_pack"]
        self.assertIn("synthesis_outline", evidence_pack)
        self.assertEqual(evidence_pack["primary_page"]["path"], "concepts/Agent-Loop.md")
        self.assertEqual(response.citations[0].vault_id, "agent-engineering")
        self.assertEqual([citation.path for citation in response.citations], ["concepts/Agent-Loop.md"])
        self.assertTrue(response.tool_trace[0].result["primary_page"])
        self.assertEqual(response.tool_trace[0].result["primary_page"]["path"], "concepts/Agent-Loop.md")
        self.assertEqual(response.tool_trace[0].result["answer_scope"]["kind"], "broad")
        self.assertEqual(response.tool_trace[0].result["answer_set"]["kind"], "multi_page")
        self.assertEqual(response.citations[0].role, "primary")
        self.assertIn("full maintained page content", response.tool_trace[0].result["primary_page"]["content"])
        self.assertEqual(response.tool_trace[0].result["supporting_pages"][0]["path"], "concepts/Session-Memory-Architecture-for-Agent-Loops.md")
        self.assertIn("production agent loops", response.tool_trace[0].result["supporting_pages"][0]["content_excerpt"])
        self.assertEqual(response.tool_trace[0].result["evidence_pack"]["recommended_action"], "answer_from_evidence")
        self.assertIn('"primary_page"', client.requests[1].messages[-1].content)
        self.assertIn('"supporting_pages"', client.requests[1].messages[-1].content)
        self.assertIn('"evidence_pack"', client.requests[1].messages[-1].content)
        self.assertNotIn('"result":', client.requests[1].messages[-1].content)
        self.assertIn("Agent Loop full maintained page content", client.requests[1].messages[-1].content)
        self.assertTrue(all(message.role != "tool" for request in client.requests for message in request.messages))
        event_types = [event.event_type for event in response.events]
        self.assertIn("model_call_started", event_types)
        self.assertIn("tool_call_finished", event_types)
        self.assertIn("final_answer_ready", event_types)

    def test_retrieval_first_searches_before_answer_for_local_model(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "Agent Loop 是由维护页面说明的推理、行动和观察循环 [1]。",
                    "citations": [
                        {"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"},
                        {"kind": "page", "path": "concepts/fake.md", "title": "Fake"},
                    ],
                }
            ],
            provider="ollama",
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(response.stats["execution_mode"], "retrieval_first")
        self.assertEqual(len(services.wiki_search.requests), 1)
        self.assertEqual(len(response.tool_trace), 1)
        self.assertEqual(response.tool_trace[0].tool, "search_wiki")
        self.assertEqual(response.stats["model_calls"], 1)
        self.assertEqual(response.stats["tool_calls"], 1)
        self.assertEqual([citation.path for citation in response.citations], ["concepts/Agent-Loop.md"])
        self.assertIn("wiki answer synthesizer", client.requests[0].messages[0].content.lower())
        self.assertIn("evidence_pack", client.requests[0].messages[-1].content)

    def test_agentic_mode_can_be_requested_for_local_model(self) -> None:
        client = FakeChatClient(
            [
                {"type": "final", "answer": "Agentic answer.", "citations": []},
            ],
            provider="ollama",
        )
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")],
                vault_path="/tmp/vault",
                execution_mode="agentic",
                append_ledger=False,
            ),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(response.stats["execution_mode"], "agentic")
        self.assertEqual(response.tool_trace, [])

    def test_unknown_tool_is_reported_in_trace(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "shell", "arguments": {"cmd": "ls"}},
                {"type": "final", "answer": "这个请求不能通过 KnoArbor 工具执行。", "citations": []},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="运行 shell")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(response.tool_trace[0].status, "error")
        self.assertIn("Unknown chat tool", response.tool_trace[0].summary)

    def test_search_evidence_pack_marks_weak_coverage(self) -> None:
        class WeakWikiSearch(FakeWikiSearch):
            def search(self, request):
                response = super().search(request)
                return response.model_copy(
                    update={
                        "primary_pages": [],
                        "supporting_pages": [],
                        "source_pages": [],
                        "results": [],
                        "answer_set": WikiAnswerSet(reason="No maintained answer page was selected.", stop_reason="no_results"),
                        "evidence_coverage": WikiEvidenceCoverage(status="weak", gap_count=1, missing_facets=["unknown"]),
                    }
                )

        @dataclass
        class WeakServices(FakeServices):
            wiki_search: WeakWikiSearch = field(default_factory=WeakWikiSearch)

        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "不存在的主题"}},
                {"type": "final", "answer": "本地知识库没有可靠覆盖。", "citations": []},
            ]
        )
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="不存在的主题是什么？")], vault_path="/tmp/vault", append_ledger=False),
            WeakServices(),  # type: ignore[arg-type]
        )

        pack = response.tool_trace[0].result["evidence_pack"]
        self.assertEqual(pack["recommended_action"], "answer_with_gap")
        self.assertEqual(pack["evidence_coverage"]["status"], "weak")
        self.assertIn("answer_with_gap", client.requests[1].messages[-1].content)

    def test_source_question_can_use_source_digest_as_primary_page(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "Agent Loop 来源"}},
                {"type": "final", "answer": "来源摘要记录了 Agent Loop 相关笔记。", "citations": []},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 的来源是什么？")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(response.tool_trace[0].result["primary_page"]["path"], "sources/Agent-Loop-Source.md")
        self.assertEqual(response.citations[0].path, "sources/Agent-Loop-Source.md")

    def test_related_page_listing_keeps_interpretive_answer_and_selected_citations(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "Agent Loop 相关页面"}},
                {
                    "type": "final",
                    "answer": "可以先看 [Agent Loop 主页面](concepts/Agent-Loop.md)，它解释循环机制；再看来源摘要 `sources/Agent-Loop-Source.md`，它用于追踪原始材料。",
                    "citations": [
                        {"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"},
                        {"kind": "page", "path": "sources/Agent-Loop-Source.md", "title": "Agent Loop Source"},
                    ],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="列出 Agent Loop 相关页面")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertIn("它解释循环机制", response.answer)
        self.assertIn("Agent Loop 主页面", response.answer)
        self.assertNotIn("[Agent Loop 主页面](", response.answer)
        self.assertNotIn("concepts/Agent-Loop.md", response.answer)
        self.assertNotIn("sources/Agent-Loop-Source.md", response.answer)
        self.assertEqual([citation.path for citation in response.citations], ["concepts/Agent-Loop.md", "sources/Agent-Loop-Source.md"])

    def test_user_can_explicitly_request_page_paths(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "Agent Loop 页面路径"}},
                {
                    "type": "final",
                    "answer": "页面路径是 `concepts/Agent-Loop.md`。",
                    "citations": [{"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 的页面路径是什么？")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertIn("concepts/Agent-Loop.md", response.answer)

    def test_repeated_tool_call_stops_loop(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "Agent Loop"}},
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "Agent Loop"}},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertIn("相同的查询步骤", response.answer)
        self.assertEqual(len(response.tool_trace), 1)
        self.assertTrue(response.warnings)

    def test_invalid_model_decision_raises_model_output_error(self) -> None:
        client = FakeChatClient(["not json"])
        service = ChatAgentService(client_factory=lambda _request: client)

        with self.assertRaises(ModelOutputError):
            service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop")], vault_path="/tmp/vault", append_ledger=False),
                FakeServices(),  # type: ignore[arg-type]
            )

    def test_chat_appends_token_ledger_records(self) -> None:
        client = FakeChatClient(
            [
                {
                    "type": "final",
                    "answer": "Agent Loop 是推理、行动和观察的循环。",
                    "citations": [{"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            response = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop")], vault_path=tmp),
                FakeServices(),  # type: ignore[arg-type]
            )
            ledger = Path(tmp) / "maintenance" / "token_ledger.jsonl"
            records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(response.stats["model_calls"], 1)
        self.assertEqual(records[0]["flow"], "chat")
        self.assertEqual(records[0]["agent"], "wiki_chat_agent")
        self.assertEqual(records[0]["page_paths"], ["concepts/Agent-Loop.md"])

    def test_chat_persists_session_and_can_continue(self) -> None:
        client = FakeChatClient(
            [
                {"type": "final", "answer": "第一轮回答。", "citations": []},
                {"type": "final", "answer": "第二轮回答。", "citations": []},
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
        second_model_messages = client.requests[-1].messages
        self.assertTrue(any(message.content == "第一轮回答。" for message in second_model_messages))
        self.assertTrue(any(message.content == "第二轮问题" for message in second_model_messages))

    def test_max_turns_returns_bounded_fallback(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "Agent Loop"}},
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "控制模式"}},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(
                messages=[ChatMessageItem(role="user", content="Agent Loop 和控制模式是什么？")],
                vault_path="/tmp/vault",
                max_turns=2,
                append_ledger=False,
            ),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertIn("工具调用上限", response.answer)
        self.assertEqual(len(response.tool_trace), 2)
        event_types = [event.event_type for event in response.events]
        self.assertIn("chat_stopped", event_types)

    def test_ambiguous_side_effect_tool_is_skipped(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "start_ingest", "arguments": {"connector_names": ["codex"]}},
                {"type": "final", "answer": "我不会直接启动知识编译，除非你明确要求执行。", "citations": []},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Codex 最近有什么内容？")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(response.tool_trace[0].tool, "start_ingest")
        self.assertEqual(response.tool_trace[0].status, "skipped")
        self.assertEqual(response.tool_trace[0].result["reason"], "explicit_user_intent_required")
        self.assertEqual(response.run_links, [])

    def test_virtual_all_vault_is_passed_as_multi_vault_search(self) -> None:
        client = FakeChatClient(
            [
                {"type": "tool_call", "tool": "search_wiki", "arguments": {"query": "Agent Loop"}},
                {"type": "final", "answer": "Agent Loop 是推理、行动和观察的循环。", "citations": []},
            ]
        )
        services = FakeServices()
        service = ChatAgentService(client_factory=lambda _request: client)
        service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_id="all", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertTrue(services.wiki_search.requests[0].all_vaults)
        self.assertIsNone(services.wiki_search.requests[0].vault_id)

    def test_explicit_memory_is_written_after_chat(self) -> None:
        client = FakeChatClient(
            [
                {
                    "type": "final",
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
                    "type": "final",
                    "answer": "我会用中文回答。",
                    "citations": [],
                },
                {
                    "type": "final",
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
