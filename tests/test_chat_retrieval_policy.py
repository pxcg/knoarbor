from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, field

from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest
from knoarbor.core.schemas.wiki_query import WikiAnswerSet, WikiEvidenceCoverage, WikiSearchResponse
from knoarbor.services.chat_agent import ChatAgentService
from tests.helpers.chat_fakes import FakeChatClient, FakeServices, FakeWikiSearch


class ChatRetrievalPolicyTest(unittest.TestCase):
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



if __name__ == "__main__":
    unittest.main()
