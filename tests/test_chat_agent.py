from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.schemas.chat import ChatCitation, ChatMessageItem, ChatRequest, ChatResponse
from knoarbor.core.errors import ModelOutputError
from knoarbor.core.schemas.wiki_query import WikiAnswerScope, WikiAnswerSet, WikiEvidenceCoverage, WikiSearchResponse, WikiSearchResult
from knoarbor.semantic.llm import ChatCompletionRequest, ChatCompletionResponse
from knoarbor.services.chat_agent import ChatAgentService
from knoarbor.services.chat_sessions import ChatSessionStore
from knoarbor.services.memory import MemoryService
from knoarbor.services.wiki_pages import WikiPageDetail, WikiPageSummary


class FakeChatClient:
    model = "fake-model"

    def __init__(self, outputs: list[dict[str, object]], *, provider: str = "fake") -> None:
        self.provider = provider
        self.outputs = list(outputs)
        self.requests: list[ChatCompletionRequest] = []

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self.requests.append(request)
        if "KnoArbor Chat Tool Planner" in request.messages[0].content:
            if self.outputs and isinstance(self.outputs[0], dict) and "tool_calls" in self.outputs[0]:
                payload = self.outputs.pop(0)
                content = json.dumps(payload, ensure_ascii=False)
                return ChatCompletionResponse(
                    content=content,
                    provider=self.provider,
                    model=self.model,
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                )
            user_text = request.messages[-1].content
            mode = "deep" if any(term in user_text for term in ["详细", "对比", "比较", "区别", "架构"]) else "balanced"
            max_results = 8 if mode == "deep" else 6
            content = json.dumps(
                {
                    "tool_calls": [{"name": "query_wiki", "arguments": {"query": user_text, "mode": mode, "max_results": max_results}}],
                    "reason": "default fake tool plan",
                    "confidence": 0.8,
                },
                ensure_ascii=False,
            )
            return ChatCompletionResponse(
                content=content,
                provider=self.provider,
                model=self.model,
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
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


class FakeWikiPages:
    def __init__(self) -> None:
        self.read_paths: list[str] = []

    def read_page(self, vault_path, relative_path, *, vault_id=None, vault_name=None):
        self.read_paths.append(relative_path)
        return WikiPageDetail(
            path=relative_path,
            vault_path=str(vault_path),
            vault_id=vault_id,
            vault_name=vault_name,
            content=f"# {relative_path}\n\nMaintained answer page content.",
            metadata={},
            summary=WikiPageSummary(
                path=relative_path,
                directory=relative_path.split("/", 1)[0],
                title=relative_path.rsplit("/", 1)[-1].removesuffix(".md"),
                summary="Maintained answer page summary.",
            ),
        )


@dataclass
class FakeServices:
    wiki_search: FakeWikiSearch = field(default_factory=FakeWikiSearch)
    wiki_pages: FakeWikiPages = field(default_factory=FakeWikiPages)
    memory: MemoryService = field(default_factory=MemoryService)
    chat_sessions: ChatSessionStore = field(default_factory=ChatSessionStore)


class ChatAgentServiceTest(unittest.TestCase):
    def test_search_then_final_answer(self) -> None:
        client = FakeChatClient(
            [
                {
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
        self.assertEqual(response.tool_trace[0].tool, "query_wiki")
        self.assertEqual(response.stats["model_calls"], 2)
        self.assertEqual(response.stats["tool_calls"], 1)
        self.assertEqual(response.stats["total_tokens"], 30)
        self.assertEqual(response.stats["retrieval_strategy"], "model_planned_tools")
        self.assertEqual(response.stats["tool_plan"]["tool_calls"][0]["arguments"]["mode"], "balanced")
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
        self.assertIn("production agent loops", response.tool_trace[0].result["supporting_pages"][0]["content"])
        self.assertEqual(response.tool_trace[0].result["evidence_pack"]["recommended_action"], "answer_from_evidence")
        self.assertEqual(
            [citation.path for citation in response.tool_trace[0].citations],
            [
                "concepts/Agent-Loop.md",
                "concepts/Session-Memory-Architecture-for-Agent-Loops.md",
                "sources/Agent-Loop-Source.md",
            ],
        )
        self.assertIn('"primary_page"', client.requests[-1].messages[-1].content)
        self.assertIn('"primary_pages"', client.requests[-1].messages[-1].content)
        self.assertIn('"supporting_pages"', client.requests[-1].messages[-1].content)
        self.assertIn('"evidence_pack"', client.requests[-1].messages[-1].content)
        self.assertNotIn('"result":', client.requests[-1].messages[-1].content)
        self.assertIn("Agent Loop full maintained page content", client.requests[-1].messages[-1].content)
        self.assertIn("Session memory supporting page content for production agent loops", client.requests[-1].messages[-1].content)
        self.assertTrue(all(message.role != "tool" for request in client.requests for message in request.messages))
        event_types = [event.event_type for event in response.events]
        self.assertIn("model_call_started", event_types)
        self.assertIn("tool_call_finished", event_types)
        self.assertIn("final_answer_ready", event_types)

    def test_searches_before_answer_for_local_model(self) -> None:
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

        self.assertEqual(response.stats["retrieval_strategy"], "model_planned_tools")
        self.assertEqual(len(services.wiki_search.requests), 1)
        self.assertEqual(len(response.tool_trace), 1)
        self.assertEqual(response.tool_trace[0].tool, "query_wiki")
        self.assertEqual(response.stats["model_calls"], 2)
        self.assertEqual(response.stats["tool_calls"], 1)
        self.assertEqual([citation.path for citation in response.citations], ["concepts/Agent-Loop.md"])
        self.assertIn("knowledge assistant", client.requests[-1].messages[0].content.lower())
        self.assertIn("evidence_pack", client.requests[-1].messages[-1].content)

    def test_provider_does_not_change_chat_retrieval_contract(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "同一个证据包由本地模型综合回答。", "citations": []},
            ],
            provider="ollama",
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")],
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(response.stats["retrieval_strategy"], "model_planned_tools")
        self.assertEqual(len(services.wiki_search.requests), 1)
        self.assertEqual(response.tool_trace[0].tool, "query_wiki")

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
                {"answer": "本地知识库没有可靠覆盖。", "citations": []},
            ]
        )
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="不存在的主题是什么？")], vault_path="/tmp/vault", append_ledger=False),
            WeakServices(),  # type: ignore[arg-type]
        )

        pack = response.tool_trace[0].result["evidence_pack"]
        self.assertEqual(pack["recommended_action"], "answer_with_gap")
        self.assertEqual(pack["evidence_coverage"]["status"], "weak")
        self.assertIn("answer_with_gap", client.requests[-1].messages[-1].content)

    def test_weak_evidence_can_trigger_second_retrieval_round(self) -> None:
        class RefiningWikiSearch(FakeWikiSearch):
            def search(self, request):
                if request.query == "unclear agent topic":
                    self.requests.append(request)
                    return WikiSearchResponse(
                        query=request.query,
                        retrieval_mode=request.mode,
                        results=[],
                        answer_set=WikiAnswerSet(reason="No maintained answer page was selected.", stop_reason="no_results"),
                        evidence_coverage=WikiEvidenceCoverage(status="weak", gap_count=1, missing_facets=["topic"]),
                        context_pack="No results",
                        warnings=[],
                    )
                return super().search(request)

        @dataclass
        class RefiningServices(FakeServices):
            wiki_search: RefiningWikiSearch = field(default_factory=RefiningWikiSearch)

        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "query_wiki", "arguments": {"query": "unclear agent topic", "mode": "balanced", "max_results": 3}}],
                    "reason": "start with the user's wording",
                    "confidence": 0.8,
                },
                {
                    "tool_calls": [{"name": "query_wiki", "arguments": {"query": "Agent Loop", "mode": "deep", "max_results": 6}}],
                    "reason": "current evidence is weak, refine the search",
                    "confidence": 0.85,
                },
                {"answer": "第二轮检索找到了 Agent Loop 维护页面。", "citations": [{"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}]},
            ]
        )
        services = RefiningServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="unclear agent topic")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual([request.query for request in services.wiki_search.requests], ["unclear agent topic", "Agent Loop"])
        self.assertEqual([item.tool for item in response.tool_trace], ["query_wiki", "query_wiki"])
        self.assertEqual(response.stats["model_calls"], 3)
        self.assertEqual(response.stats["tool_calls"], 2)
        self.assertEqual(response.stats["evidence_rounds"], 2)
        self.assertEqual(response.stats["evidence_stop_reason"], "evidence_sufficient")
        self.assertEqual(len(response.stats["tool_plans"]), 2)
        self.assertEqual(response.citations[0].path, "concepts/Agent-Loop.md")
        second_plan_messages = client.requests[1].messages
        current_context = [message.content for message in second_plan_messages if message.content.startswith("Current turn evidence context:")]
        self.assertEqual(len(current_context), 1)
        self.assertIn('"needs_more_evidence": true', current_context[0])
        self.assertIn('"recommended_next_step": "query_wiki"', current_context[0])
        self.assertIn('"executed_queries": ["unclear agent topic"]', current_context[0])

    def test_source_question_can_use_source_digest_as_primary_page(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "来源摘要记录了 Agent Loop 相关笔记。", "citations": []},
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
                {
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
                {
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

        self.assertEqual(response.stats["model_calls"], 2)
        self.assertEqual(records[0]["flow"], "chat")
        self.assertEqual(records[0]["agent"], "wiki_chat_agent")
        self.assertIn("concepts/Agent-Loop.md", records[0]["page_paths"])
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
        self.assertTrue(any(message.content == "第一轮回答。" for message in second_model_messages))
        self.assertTrue(any(message.content == "第二轮问题" for message in second_model_messages))

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
                citations=[ChatCitation(kind="page", path="concepts/First.md", title="First")],
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
                citations=[ChatCitation(kind="page", path="concepts/Second.md", title="Second")],
            )
            store.persist_response(tmp, response=first, request_messages=first.messages, vault_id="test", vault_name="Test")
            record = store.persist_response(tmp, response=second, request_messages=second.messages, vault_id="test", vault_name="Test")

        self.assertEqual(len(record.turns), 2)
        self.assertEqual(record.turns[0].citations[0].path, "concepts/First.md")
        self.assertEqual(record.turns[1].citations[0].path, "concepts/Second.md")
        self.assertEqual(record.citations[0].path, "concepts/Second.md")

    def test_followup_can_reuse_prior_evidence(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "Agent Loop 是推理、行动和观察的循环。", "citations": [{"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}]},
                {
                    "tool_calls": [
                        {
                            "name": "reuse_context",
                            "arguments": {"page_paths": ["concepts/Agent-Loop.md"]},
                        }
                    ],
                    "reason": "follow-up can reuse prior evidence",
                    "confidence": 0.9,
                },
                {"answer": "它和 OpenClaw 的关系可以基于上一轮证据解释。", "citations": [{"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}]},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            second = service.chat(
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="那它和 OpenClaw 有什么区别？")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(len(services.wiki_search.requests), 1)
        self.assertEqual(second.tool_trace[0].tool, "reuse_context")
        self.assertEqual(second.stats["tool_plan"]["tool_calls"][0]["name"], "reuse_context")
        second_plan_messages = client.requests[-2].messages
        prior_context = [message.content for message in second_plan_messages if message.content.startswith("Prior evidence context:")]
        self.assertEqual(len(prior_context), 1)
        self.assertIn('"answer_page_paths": ["concepts/Agent-Loop.md", "concepts/Session-Memory-Architecture-for-Agent-Loops.md"]', prior_context[0])
        self.assertIn('"source_page_paths": ["sources/Agent-Loop-Source.md"]', prior_context[0])
        self.assertIn('"preferred_read_pages": ["concepts/Agent-Loop.md", "concepts/Session-Memory-Architecture-for-Agent-Loops.md"]', prior_context[0])

    def test_followup_source_digest_read_prefers_prior_answer_page(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "Agent Loop 是推理、行动和观察的循环。", "citations": [{"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}]},
                {
                    "tool_calls": [
                        {
                            "name": "read_wiki_page",
                            "arguments": {"page_path": "sources/Agent-Loop-Source.md"},
                        }
                    ],
                    "reason": "model picked the source digest by mistake",
                    "confidence": 0.8,
                },
                {"answer": "控制模式来自维护后的概念页面。", "citations": [{"kind": "page", "path": "concepts/Agent-Loop.md", "title": "Agent Loop"}]},
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            second = service.chat(
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="再展开讲一下控制模式")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(services.wiki_pages.read_paths, ["concepts/Agent-Loop.md"])
        self.assertIn("instead of source digest sources/Agent-Loop-Source.md", second.tool_trace[0].summary)
        self.assertEqual(second.tool_trace[0].citations[0].path, "concepts/Agent-Loop.md")

    def test_answer_directly_is_guarded_for_knowledge_questions(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "answer_directly", "arguments": {"reason": "planner mistake"}}],
                    "reason": "mistaken direct answer",
                    "confidence": 0.9,
                },
                {"answer": "Agent Loop 需要基于知识库回答。", "citations": []},
            ]
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(len(services.wiki_search.requests), 1)
        self.assertEqual(response.tool_trace[0].tool, "query_wiki")
        self.assertEqual(response.stats["tool_plan"]["tool_calls"][0]["name"], "query_wiki")

    def test_answer_directly_is_allowed_for_greetings(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "answer_directly", "arguments": {"reason": "greeting"}}],
                    "reason": "greeting",
                    "confidence": 0.9,
                },
                {"answer": "你好，我可以帮助你查询和解释 KnoArbor 知识库。", "citations": []},
            ]
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="你好")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(len(services.wiki_search.requests), 0)
        self.assertEqual(response.tool_trace[0].tool, "answer_directly")

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
        self.assertEqual(updated.last_ingest_run_id, "20260615_test")
        self.assertIsNotNone(updated.last_ingested_at)

    def test_virtual_all_vault_is_passed_as_multi_vault_search(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "Agent Loop 是推理、行动和观察的循环。", "citations": []},
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

    def test_chat_retrieval_policy_uses_deep_for_broad_questions(self) -> None:
        client = FakeChatClient([{"answer": "系统回答。", "citations": []}])
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="请系统详细对比 Agent Loop 和多智能体编排架构的区别")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(services.wiki_search.requests[0].mode, "deep")
        self.assertEqual(services.wiki_search.requests[0].max_results, 8)
        self.assertEqual(response.stats["tool_plan"]["reason"], "default fake tool plan")

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
