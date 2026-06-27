from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from knoarbor.core.errors import ExternalServiceError
from knoarbor.core.schemas.chat import ChatCitation, ChatMessageItem, ChatRequest, ChatResponse
from knoarbor.core.schemas.vaults import VaultListResponse, VaultProfile
from knoarbor.core.schemas.wiki_query import WikiAnswerScope, WikiAnswerSet, WikiAtomTrace, WikiEvidenceCoverage, WikiSearchResponse, WikiSearchResult
from knoarbor.entrypoints.api import create_app
from knoarbor.semantic.llm import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionStreamChunk
from knoarbor.services import ApplicationServices
from knoarbor.services.chat_answer import parse_answer_draft
from knoarbor.services.chat_agent import ChatAgentService
from knoarbor.services.chat_sessions import ChatSessionStore
from knoarbor.services.memory import MemoryService
from knoarbor.services.wiki_pages import WikiPageDetail, WikiPageRelation, WikiPageRelationsResponse, WikiPageSummary, WikiPagesResponse


class FakeChatClient:
    model = "fake-model"

    def __init__(self, outputs: list[dict[str, object]], *, provider: str = "fake") -> None:
        self.provider = provider
        self.outputs = list(outputs)
        self.requests: list[ChatCompletionRequest] = []
        self.failures_before_success: list[Exception] = []

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self.requests.append(request)
        if self.failures_before_success:
            raise self.failures_before_success.pop(0)
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
        elif request.structured_output is False and "answer" in payload:
            content = str(payload["answer"])
        else:
            content = json.dumps(payload, ensure_ascii=False)
        return ChatCompletionResponse(
            content=content,
            provider=self.provider,
            model=self.model,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    def stream(self, request: ChatCompletionRequest):
        response = self.complete(request)
        midpoint = max(1, len(response.content) // 2)
        for delta in (response.content[:midpoint], response.content[midpoint:]):
            if delta:
                yield ChatCompletionStreamChunk(delta=delta)
        yield ChatCompletionStreamChunk(response=response)


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
                    page_role="source",
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
                    path="Agent-Loop.md",
                    title="Agent Loop",
                    page_role="primary",
                    score=9.0,
                    relevance="high",
                    match_kind="direct",
                    reason="title match",
                    summary="Agent loop alternates reasoning, action, and observation.",
                    content="Agent Loop full maintained page content.",
                    vault_id="agent-engineering",
                    vault_name="Agent Engineering",
                    atom_traces=[
                        WikiAtomTrace(
                            atom_id="claim_agent_loop_cycle",
                            atom_type="claim",
                            text="Agent loop alternates reasoning, action, and observation.",
                            source_digest_id="sd_agent_loop",
                        )
                    ],
                ),
                WikiSearchResult(
                    path="Session-Memory-Architecture-for-Agent-Loops.md",
                    title="Session Memory Architecture for Agent Loops",
                    page_role="supporting",
                    score=7.0,
                    relevance="medium",
                    match_kind="related",
                    reason="related implementation page",
                    summary="Session memory explains production support for agent loops.",
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
                primary_paths=["Agent-Loop.md"],
                supporting_paths=["Session-Memory-Architecture-for-Agent-Loops.md"],
                source_paths=["sources/Agent-Loop-Source.md"],
            ),
            evidence_coverage=WikiEvidenceCoverage(status="strong", primary_count=1, supporting_count=1, source_count=1),
            context_pack="Agent Loop context",
            response_guidance=[],
            warnings=[],
        )


class FakeWikiPages:
    def __init__(self) -> None:
        self.read_paths: list[str] = []
        self.list_calls = 0
        self.link_paths: list[str] = []

    def list_pages(self, vault_path, *, vault_id=None, vault_name=None):
        self.list_calls += 1
        return WikiPagesResponse(
            vault_path=str(vault_path),
            vault_id=vault_id,
            vault_name=vault_name,
            pages=[
                WikiPageSummary(
                    path="Agent-Loop.md",
                    directory="pages",
                    title="Agent Loop",
                    summary="Agent loop alternates reasoning, action, and observation.",
                    headings=["Summary", "Control patterns"],
                ),
                WikiPageSummary(
                    path="OpenClaw.md",
                    directory="pages",
                    title="OpenClaw",
                    summary="OpenClaw is an engineering agent platform.",
                    headings=["Summary"],
                ),
            ],
        )

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

    def page_relations(self, vault_path, relative_path, *, vault_id=None, vault_name=None):
        self.link_paths.append(relative_path)
        return WikiPageRelationsResponse(
            path=relative_path,
            vault_path=str(vault_path),
            vault_id=vault_id,
            vault_name=vault_name,
            outgoing_pages=[
                WikiPageRelation(source=relative_path, target="OpenClaw", target_path="OpenClaw.md", resolved=True),
            ],
            incoming_pages=[
                WikiPageRelation(source="Agent-Engineering.md", target="Agent Loop", target_path=relative_path, resolved=True),
            ],
        )


class FakeVaults:
    def list_vaults(self, *, config_path=None):
        return VaultListResponse(
            config_path=config_path,
            default_vault_id="agent-engineering",
            vaults=[
                VaultProfile(id="agent-engineering", name="Agent Engineering", path="/tmp/vault", active=True, exists=True),
                VaultProfile(id="rag", name="RAG Notes", path="/tmp/rag", active=False, exists=True),
            ],
        )


@dataclass
class FakeServices:
    wiki_search: FakeWikiSearch = field(default_factory=FakeWikiSearch)
    wiki_pages: FakeWikiPages = field(default_factory=FakeWikiPages)
    vaults: FakeVaults = field(default_factory=FakeVaults)
    memory: MemoryService = field(default_factory=MemoryService)
    chat_sessions: ChatSessionStore = field(default_factory=ChatSessionStore)


class ChatAgentServiceTest(unittest.TestCase):
    def test_answer_citation_page_roles_are_preserved(self) -> None:
        draft = parse_answer_draft(
            json.dumps(
                {
                    "answer": "Agent Loop answer.",
                    "citations": [
                        {"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"},
                        {"kind": "page", "path": "OpenClaw.md", "title": "OpenClaw"},
                    ],
                }
            )
        )

        self.assertEqual([citation.kind for citation in draft.citations], ["page", "page"])

    def test_search_then_final_answer(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "Agent Loop 是推理、行动和观察的循环。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
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
        self.assertEqual(response.citations[0].path, "Agent-Loop.md")
        evidence_pack = response.tool_trace[0].result["evidence_pack"]
        self.assertIn("synthesis_outline", evidence_pack)
        self.assertEqual(evidence_pack["primary_page"]["path"], "Agent-Loop.md")
        self.assertEqual(response.citations[0].vault_id, "agent-engineering")
        self.assertEqual(
            [citation.path for citation in response.citations],
            [
                "Agent-Loop.md",
                "Session-Memory-Architecture-for-Agent-Loops.md",
                "sources/Agent-Loop-Source.md",
            ],
        )
        self.assertTrue(response.tool_trace[0].result["primary_page"])
        self.assertEqual(response.tool_trace[0].result["primary_page"]["path"], "Agent-Loop.md")
        self.assertEqual(response.tool_trace[0].result["answer_scope"]["kind"], "broad")
        self.assertEqual(response.tool_trace[0].result["answer_set"]["kind"], "multi_page")
        self.assertEqual(response.citations[0].role, "primary")
        self.assertIn("full maintained page content", response.tool_trace[0].result["primary_page"]["content"])
        self.assertEqual(response.tool_trace[0].result["primary_page"]["atom_traces"][0]["atom_id"], "fact_agent_loop_cycle")
        self.assertEqual(evidence_pack["primary_page"]["atom_traces"][0]["atom_id"], "fact_agent_loop_cycle")
        self.assertEqual(evidence_pack["citation_pages"][0]["atom_traces"][0]["source_digest_id"], "sd_agent_loop")
        self.assertEqual(response.tool_trace[0].result["supporting_pages"][0]["path"], "Session-Memory-Architecture-for-Agent-Loops.md")
        self.assertIn("production agent loops", response.tool_trace[0].result["supporting_pages"][0]["content"])
        self.assertEqual(response.tool_trace[0].result["evidence_pack"]["recommended_action"], "answer_from_evidence")
        self.assertEqual(
            [citation.path for citation in response.tool_trace[0].citations],
            [
                "Agent-Loop.md",
                "Session-Memory-Architecture-for-Agent-Loops.md",
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

    def test_chat_stream_endpoint_emits_progress_and_final_response(self) -> None:
        client_model = FakeChatClient(
            [
                {
                    "answer": "Agent Loop 是推理、行动和观察的循环。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        services = ApplicationServices(
            chat=ChatAgentService(client_factory=lambda _request: client_model),
            chat_sessions=ChatSessionStore(),
            wiki_search=FakeWikiSearch(),  # type: ignore[arg-type]
            wiki_pages=FakeWikiPages(),  # type: ignore[arg-type]
            vaults=FakeVaults(),  # type: ignore[arg-type]
            memory=MemoryService(),
        )
        app = create_app(services)
        with tempfile.TemporaryDirectory() as tmp:
            response = TestClient(app).post(
                "/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "Agent Loop 是什么？"}],
                    "vault_path": tmp,
                    "append_ledger": False,
                    "include_trace": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
        body = response.text
        self.assertIn("event: stage", body)
        self.assertIn("event: tool", body)
        self.assertIn("event: answer_delta", body)
        self.assertIn("event: final", body)
        self.assertIn('"schema_version": "chat_response.v1"', body)
        self.assertIn("Agent Loop 是推理", body)

    def test_chat_model_calls_retry_retryable_transport_errors(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "Agent Loop 是推理、行动和观察的循环。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        client.failures_before_success = [ExternalServiceError("temporary TLS error")]
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertIn("Agent Loop", response.answer)
        self.assertEqual(client.requests[0].messages[0].content, client.requests[1].messages[0].content)
        self.assertEqual(response.stats["model_calls"], 2)
        self.assertEqual(response.stats["tool_calls"], 1)

    def test_searches_before_answer_for_local_model(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "Agent Loop 是由维护页面说明的推理、行动和观察循环 [1]。",
                    "citations": [
                        {"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"},
                        {"kind": "page", "path": "fake.md", "title": "Fake"},
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
        self.assertEqual(
            [citation.path for citation in response.citations],
            [
                "Agent-Loop.md",
            ],
        )
        self.assertIn("knowledge assistant", client.requests[-1].messages[0].content.lower())
        self.assertIn("evidence_pack", client.requests[-1].messages[-1].content)

    def test_answer_directly_plan_is_not_forced_to_query(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "answer_directly", "arguments": {"reason": "identity question"}}],
                    "reason": "assistant identity does not need wiki evidence",
                    "confidence": 0.95,
                },
                {"answer": "你好，我是 KnoArbor 的知识助手，可以帮助你查询和整理本地知识库。", "citations": []},
            ]
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="你好，你是谁，有什么功能？")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(response.tool_trace[0].tool, "answer_directly")
        self.assertEqual(response.stats["tool_calls"], 1)
        self.assertEqual(response.citations, [])
        self.assertEqual(services.wiki_search.requests, [])

    def test_read_wiki_page_resolves_title_like_page_reference(self) -> None:
        class PageReferenceWikiPages(FakeWikiPages):
            def list_pages(self, vault_path, *, vault_id=None, vault_name=None):
                response = super().list_pages(vault_path, vault_id=vault_id, vault_name=vault_name)
                return response.model_copy(
                    update={
                        "pages": [
                            *response.pages,
                            WikiPageSummary(
                                path="Agent-Engineering.md",
                                directory="pages",
                                title="Agent Engineering",
                                summary="Agent engineering covers agent loop, tools, and runtime design.",
                                headings=["Summary"],
                            ),
                        ]
                    }
                )

        @dataclass
        class PageReferenceServices(FakeServices):
            wiki_pages: PageReferenceWikiPages = field(default_factory=PageReferenceWikiPages)

        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "read_wiki_page", "arguments": {"page_path": "Agent-Engineering.md"}}],
                    "reason": "read a known page by title-like reference",
                    "confidence": 0.9,
                },
                {"answer": "Agent Engineering 页面已读取。", "citations": [{"kind": "page", "path": "Agent-Engineering.md", "title": "Agent Engineering"}]},
            ]
        )
        services = PageReferenceServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="展开 Agent Engineering 页面")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(services.wiki_pages.read_paths, ["Agent-Engineering.md"])
        self.assertIn("resolving requested page reference Agent-Engineering.md", response.tool_trace[0].summary)
        self.assertEqual(response.citations[0].path, "Agent-Engineering.md")

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
                        "evidence_coverage": WikiEvidenceCoverage(status="weak", gap_count=1, missing_dimensions=["unknown"]),
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
                        evidence_coverage=WikiEvidenceCoverage(status="weak", gap_count=1, missing_dimensions=["topic"]),
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
                {"answer": "第二轮检索找到了 Agent Loop 维护页面。", "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}]},
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
        self.assertEqual(response.citations[0].path, "Agent-Loop.md")
        second_plan_messages = client.requests[1].messages
        planning_state = json.loads(second_plan_messages[-1].content)["planning_state"]
        current_context = planning_state["current_turn_evidence_context"]
        self.assertTrue(current_context["summary"]["needs_more_evidence"])
        self.assertEqual(current_context["summary"]["recommended_next_step"], "query_wiki")
        self.assertEqual(current_context["summary"]["executed_queries"], ["unclear agent topic"])

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

    def test_related_page_listing_keeps_interpretive_answer_and_trace_citations(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "可以先看 [Agent Loop 主页面](Agent-Loop.md)，它解释循环机制；再看来源摘要 `sources/Agent-Loop-Source.md`，它用于追踪原始材料。",
                    "citations": [
                        {"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"},
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
        self.assertNotIn("Agent-Loop.md", response.answer)
        self.assertNotIn("sources/Agent-Loop-Source.md", response.answer)
        self.assertEqual(
            [citation.path for citation in response.citations],
            [
                "Agent-Loop.md",
                "Session-Memory-Architecture-for-Agent-Loops.md",
                "sources/Agent-Loop-Source.md",
            ],
        )

    def test_user_can_explicitly_request_page_paths(self) -> None:
        client = FakeChatClient(
            [
                {
                    "answer": "页面路径是 `Agent-Loop.md`。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 的页面路径是什么？")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertIn("Agent-Loop.md", response.answer)

    def test_plain_markdown_answer_is_allowed(self) -> None:
        client = FakeChatClient(["not json"])
        service = ChatAgentService(client_factory=lambda _request: client)

        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(response.answer, "not json")

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

    def test_followup_can_reuse_prior_evidence(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "Agent Loop 是推理、行动和观察的循环。", "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}]},
                {
                    "tool_calls": [
                        {
                            "name": "reuse_context",
                            "arguments": {"page_paths": ["Agent-Loop.md"]},
                        }
                    ],
                    "reason": "follow-up can reuse prior evidence",
                    "confidence": 0.9,
                },
                {"answer": "它和 OpenClaw 的关系可以基于上一轮证据解释。", "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}]},
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
        prior_context = json.loads(second_plan_messages[-1].content)["planning_state"]["prior_evidence_context"]
        self.assertEqual(prior_context["answer_page_paths"], ["Agent-Loop.md", "Session-Memory-Architecture-for-Agent-Loops.md"])
        self.assertEqual(prior_context["source_page_paths"], ["sources/Agent-Loop-Source.md"])
        self.assertEqual(prior_context["preferred_read_pages"], ["Agent-Loop.md", "Session-Memory-Architecture-for-Agent-Loops.md"])

    def test_synthesis_followup_overrides_new_search_to_reuse_session_evidence(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "Agent Loop 是推理、行动和观察的循环。", "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}]},
                {
                    "tool_calls": [
                        {
                            "name": "query_wiki",
                            "arguments": {"query": "技术设计文档大纲", "mode": "balanced", "max_results": 6},
                        }
                    ],
                    "reason": "model tried a broad literal search",
                    "confidence": 0.8,
                },
                {"answer": "这是基于前面证据整理的设计文档大纲。", "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}]},
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
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="最后，请把前面整个方案整理成技术设计文档大纲。")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(len(services.wiki_search.requests), 1)
        self.assertEqual(second.tool_trace[0].tool, "reuse_context")
        self.assertEqual(second.stats["tool_plan"]["tool_calls"][0]["name"], "reuse_context")
        self.assertEqual(second.stats["plan_adjustments"][0]["kind"], "context_synthesis_reuse")
        answer_prompt = client.requests[-1].messages[-1].content
        self.assertIn('"kind": "session_evidence"', answer_prompt)
        self.assertIn("Session memory supporting page content for production agent loops", answer_prompt)

    def test_followup_source_digest_read_prefers_prior_answer_page(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "Agent Loop 是推理、行动和观察的循环。", "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}]},
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
                {"answer": "控制模式来自维护后的概念页面。", "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}]},
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

        self.assertEqual(services.wiki_pages.read_paths, ["Agent-Loop.md"])
        self.assertIn("instead of source digest sources/Agent-Loop-Source.md", second.tool_trace[0].summary)
        self.assertEqual(second.tool_trace[0].citations[0].path, "Agent-Loop.md")

    def test_reference_question_keeps_source_digest_read(self) -> None:
        client = FakeChatClient(
            [
                {"answer": "Agent Loop 是推理、行动和观察的循环。", "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}]},
                {
                    "tool_calls": [
                        {
                            "name": "read_wiki_page",
                            "arguments": {"page_path": "sources/Agent-Loop-Source.md"},
                        }
                    ],
                    "reason": "read a reference source page",
                    "confidence": 0.85,
                },
                {"answer": "这个来源页更适合作为辅助参考。", "citations": [{"kind": "page", "path": "sources/Agent-Loop-Source.md", "title": "Agent Loop Source"}]},
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
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="这些参考页面哪些适合作为核心实现依据？")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(services.wiki_pages.read_paths, ["sources/Agent-Loop-Source.md"])
        self.assertEqual(second.tool_trace[0].summary, "Read wiki page sources/Agent-Loop-Source.md.")
        self.assertEqual(second.tool_trace[0].citations[0].path, "sources/Agent-Loop-Source.md")

    def test_broad_question_can_start_with_anchor_page_then_expand_evidence(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [
                        {
                            "name": "read_wiki_page",
                            "arguments": {"page_path": "Agent-Loop.md"},
                        }
                    ],
                    "reason": "model picked an anchor page",
                    "confidence": 0.8,
                },
                {
                    "tool_calls": [
                        {
                            "name": "finish_answer",
                            "arguments": {"reason": "anchor page is enough"},
                        }
                    ],
                    "reason": "model tried to finish from one anchor page",
                    "confidence": 0.85,
                },
                {
                    "answer": "工程化 Agent 架构需要综合 Agent Loop、工具、记忆和监控页面。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                messages=[ChatMessageItem(role="user", content="帮我设计一个生产级工程 Agent 系统架构，包含工具、记忆、路由和监控。")],
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual([item.tool for item in response.tool_trace], ["read_wiki_page", "query_wiki"])
        self.assertEqual(services.wiki_pages.read_paths, ["Agent-Loop.md"])
        self.assertEqual(services.wiki_search.requests[0].mode, "deep")
        self.assertEqual(response.stats["plan_adjustments"][0]["kind"], "anchor_page_needs_supporting_evidence")
        self.assertEqual(response.stats["tool_plan"]["tool_calls"][0]["name"], "read_wiki_page")

    def test_single_page_read_for_broad_followup_requires_more_evidence(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [
                        {
                            "name": "read_wiki_page",
                            "arguments": {"page_path": "Agent-Loop.md"},
                        }
                    ],
                    "reason": "read a page first",
                    "confidence": 0.8,
                },
                {
                    "tool_calls": [
                        {
                            "name": "finish_answer",
                            "arguments": {"reason": "single page is enough"},
                        }
                    ],
                    "reason": "single page is not enough for the broad architecture question",
                    "confidence": 0.85,
                },
                {
                    "answer": "生产级 Agent 架构需要综合多个页面。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
                },
            ]
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                messages=[ChatMessageItem(role="user", content="从工程、工具、记忆、路由和监控几个方面设计 Agent 系统。")],
                vault_path="/tmp/vault",
                append_ledger=False,
                max_turns=4,
            ),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual([item.tool for item in response.tool_trace], ["read_wiki_page", "query_wiki"])
        self.assertEqual(services.wiki_pages.read_paths, ["Agent-Loop.md"])
        self.assertEqual(len(services.wiki_search.requests), 1)
        self.assertEqual(response.stats["plan_adjustments"][0]["kind"], "anchor_page_needs_supporting_evidence")

    def test_answer_directly_plan_is_respected(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "answer_directly", "arguments": {"reason": "assistant capability question"}}],
                    "reason": "direct assistant answer",
                    "confidence": 0.9,
                },
                {"answer": "你好，我可以帮助你查询和解释 KnoArbor 知识库。", "citations": []},
            ]
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="你有什么功能？")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(len(services.wiki_search.requests), 0)
        self.assertEqual(response.tool_trace[0].tool, "answer_directly")
        self.assertEqual(response.stats["tool_plan"]["tool_calls"][0]["name"], "answer_directly")

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
        self.assertIsNotNone(closed.ingest_candidate)
        self.assertFalse(closed.ingest_candidate.should_ingest)
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

    def test_chat_can_list_wiki_pages(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "list_wiki_pages", "arguments": {"query": "Agent", "max_results": 10}}],
                    "reason": "user asks for available pages",
                    "confidence": 0.9,
                },
                {"answer": "当前有 Agent Loop 页面。", "citations": []},
            ]
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent 相关页面有哪些？")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(services.wiki_pages.list_calls, 1)
        self.assertEqual(response.tool_trace[0].tool, "list_wiki_pages")
        self.assertEqual(response.tool_trace[0].result["returned_pages"], 1)
        self.assertEqual(response.tool_trace[0].result["pages"][0]["path"], "Agent-Loop.md")
        self.assertEqual(response.citations, [])
        self.assertEqual(response.hidden_evidence_count, 1)
        self.assertIn('"pages"', client.requests[-1].messages[-1].content)

    def test_chat_can_inspect_wiki_relations(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "inspect_wiki_relations", "arguments": {"page_path": "Agent-Loop.md"}}],
                    "reason": "user asks for page relationships",
                    "confidence": 0.9,
                },
                {"answer": "Agent Loop 关联 OpenClaw 和 Agent Engineering。", "citations": []},
            ]
        )
        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop 这个页面和哪些页面有关？")], vault_path="/tmp/vault", append_ledger=False),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(services.wiki_pages.link_paths, ["Agent-Loop.md"])
        self.assertEqual(response.tool_trace[0].tool, "inspect_wiki_relations")
        self.assertEqual(response.tool_trace[0].result["outgoing_pages"][0]["target_path"], "OpenClaw.md")
        self.assertEqual(response.citations, [])
        self.assertEqual(response.hidden_evidence_count, 2)
        self.assertIn('"outgoing_pages"', client.requests[-1].messages[-1].content)

    def test_chat_can_list_vaults(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "list_vaults", "arguments": {}}],
                    "reason": "user asks for configured vaults",
                    "confidence": 0.9,
                },
                {"answer": "当前有 Agent Engineering 和 RAG Notes。", "citations": []},
            ]
        )
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="我现在有哪些知识库？")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(response.tool_trace[0].tool, "list_vaults")
        self.assertEqual(response.tool_trace[0].result["default_vault_id"], "agent-engineering")
        self.assertEqual(response.tool_trace[0].result["vaults"][0]["name"], "Agent Engineering")
        self.assertIn('"vaults"', client.requests[-1].messages[-1].content)

    def test_complex_agent_design_chat_uses_query_read_links_list_and_reuse(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [
                        {
                            "name": "query_wiki",
                            "arguments": {
                                "query": "Agent Loop multi-agent orchestration memory architecture",
                                "mode": "deep",
                                "max_results": 8,
                            },
                        }
                    ],
                    "reason": "start from the broad architecture topic",
                    "confidence": 0.9,
                },
                {
                    "answer": "Agent Loop 架构需要把循环控制、记忆和编排分层处理。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
                },
                {
                    "tool_calls": [
                        {
                            "name": "read_wiki_page",
                            "arguments": {"page_path": "Session-Memory-Architecture-for-Agent-Loops.md"},
                        }
                    ],
                    "reason": "follow-up asks for memory details from a known supporting page",
                    "confidence": 0.9,
                },
                {
                    "answer": "记忆层应覆盖短期会话、压缩摘要和可恢复状态。",
                    "citations": [
                        {
                            "kind": "page",
                            "path": "Session-Memory-Architecture-for-Agent-Loops.md",
                            "title": "Session Memory Architecture for Agent Loops",
                        }
                    ],
                },
                {
                    "tool_calls": [
                        {
                            "name": "inspect_wiki_relations",
                            "arguments": {"page_path": "Agent-Loop.md"},
                        }
                    ],
                    "reason": "user asks for related implementation pages",
                    "confidence": 0.9,
                },
                {
                    "answer": "Agent Loop 页面关联 OpenClaw 和 Agent Engineering，可作为实现参考。",
                    "citations": [{"kind": "page", "path": "OpenClaw.md", "title": "OpenClaw"}],
                },
                {
                    "tool_calls": [
                        {
                            "name": "list_wiki_pages",
                            "arguments": {"query": "Agent", "max_results": 20},
                        }
                    ],
                    "reason": "user asks for available agent pages before final synthesis",
                    "confidence": 0.9,
                },
                {
                    "answer": "可参考 Agent Loop 与 OpenClaw 两类页面组织方案。",
                    "citations": [{"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"}],
                },
                {
                    "tool_calls": [
                        {
                            "name": "query_wiki",
                            "arguments": {"query": "agent architecture design document", "mode": "deep", "max_results": 8},
                        }
                    ],
                    "reason": "model attempted a broad final search",
                    "confidence": 0.8,
                },
                {
                    "answer": "最终方案应分为入口层、循环控制层、工具层、记忆层和治理层，并基于前面页面证据综合。",
                    "citations": [
                        {"kind": "page", "path": "Agent-Loop.md", "title": "Agent Loop"},
                        {
                            "kind": "page",
                            "path": "Session-Memory-Architecture-for-Agent-Loops.md",
                            "title": "Session Memory Architecture for Agent Loops",
                        },
                    ],
                },
            ]
        )
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="基于我的 Agent 相关页面，设计一个生产级工程 Agent 架构。")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            second = service.chat(
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="继续展开它的会话记忆和上下文管理。")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            third = service.chat(
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="Agent Loop 页面还关联哪些实现页面？")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            fourth = service.chat(
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="列出还能参考的 Agent 相关页面。")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )
            fifth = service.chat(
                ChatRequest(session_id=first.session_id, messages=[ChatMessageItem(role="user", content="最后，把前面内容整理成一份工程 Agent 技术设计方案。")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(first.tool_trace[0].tool, "query_wiki")
        self.assertEqual(first.tool_trace[0].arguments["mode"], "deep")
        self.assertEqual(second.tool_trace[0].tool, "read_wiki_page")
        self.assertEqual(services.wiki_pages.read_paths, ["Session-Memory-Architecture-for-Agent-Loops.md"])
        self.assertEqual(third.tool_trace[0].tool, "inspect_wiki_relations")
        self.assertEqual(services.wiki_pages.link_paths, ["Agent-Loop.md"])
        self.assertEqual(fourth.tool_trace[0].tool, "list_wiki_pages")
        self.assertEqual(services.wiki_pages.list_calls, 1)
        self.assertEqual(fifth.tool_trace[0].tool, "reuse_context")
        self.assertEqual(fifth.stats["tool_plan"]["tool_calls"][0]["name"], "reuse_context")
        self.assertEqual(fifth.stats["plan_adjustments"][0]["kind"], "context_synthesis_reuse")
        self.assertEqual([request.query for request in services.wiki_search.requests], ["Agent Loop multi-agent orchestration memory architecture"])
        self.assertIn('"kind": "session_evidence"', client.requests[-1].messages[-1].content)
        self.assertIn("Session-Memory-Architecture-for-Agent-Loops.md", client.requests[-1].messages[-1].content)
        self.assertIn("入口层、循环控制层、工具层、记忆层和治理层", fifth.answer)
        self.assertEqual(
            [citation.path for citation in fifth.citations],
            [
                "Agent-Loop.md",
                "Session-Memory-Architecture-for-Agent-Loops.md",
                "sources/Agent-Loop-Source.md",
            ],
        )
        planner_requests = [request for request in client.requests if "KnoArbor Chat Tool Planner" in request.messages[0].content]
        self.assertTrue(planner_requests)
        for planner_request in planner_requests:
            planner_payload = "\n".join(message.content for message in planner_request.messages)
            self.assertIn("planning_state", planner_payload)
            self.assertNotIn("可参考 Agent Loop 与 OpenClaw 两类页面组织方案", planner_payload)
            self.assertNotIn("最终方案应分为入口层、循环控制层、工具层、记忆层和治理层", planner_payload)
        answer_requests = [request for request in client.requests if "knowledge assistant" in request.messages[0].content.lower()]
        self.assertTrue(answer_requests)
        for answer_request in answer_requests:
            answer_payload = "\n".join(message.content for message in answer_request.messages)
            self.assertIn("answer_state", answer_payload)
        final_answer_state = json.loads(answer_requests[-1].messages[-1].content)["answer_state"]
        self.assertIn("可参考 Agent Loop 与 OpenClaw 两类页面组织方案", json.dumps(final_answer_state["conversation_context"], ensure_ascii=False))

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
