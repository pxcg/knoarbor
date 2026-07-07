from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from knoarbor.core.errors import ExternalServiceError
from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest
from knoarbor.entrypoints.api import create_app
from knoarbor.services import ApplicationServices
from knoarbor.services.chat_agent import ChatAgentService
from knoarbor.services.chat_sessions import ChatSessionStore
from knoarbor.services.memory import MemoryService
from knoarbor.services.wiki_pages import WikiPageSummary, WikiPagesResponse
from tests.helpers.chat_fakes import FakeChatClient, FakeServices, FakeVaults, FakeWikiPages, FakeWikiSearch


class ChatAgentServiceTest(unittest.TestCase):
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
        self.assertEqual(response.tool_trace[0].result["primary_page"]["atom_traces"][0]["atom_id"], "claim_agent_loop_cycle")
        self.assertEqual(evidence_pack["primary_page"]["atom_traces"][0]["atom_id"], "claim_agent_loop_cycle")
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
        self.assertIn("Read wiki page Agent-Engineering.md", response.tool_trace[0].summary)
        self.assertEqual(response.citations[0].path, "Agent-Engineering.md")

    def test_plain_markdown_answer_is_allowed(self) -> None:
        client = FakeChatClient(["not json"])
        service = ChatAgentService(client_factory=lambda _request: client)

        response = service.chat(
            ChatRequest(messages=[ChatMessageItem(role="user", content="Agent Loop")], vault_path="/tmp/vault", append_ledger=False),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(response.answer, "not json")

    def test_response_style_is_injected_only_for_answer_synthesis(self) -> None:
        client = FakeChatClient([{"answer": "详细回答。", "citations": []}])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            vault.mkdir()
            config = root / "config.yaml"
            config.write_text(
                f"""
vault:
  path: {vault}
chat:
  response_style: deep
models:
  providers: {{}}
image_generation:
  providers: {{}}
""",
                encoding="utf-8",
            )

            response = service.chat(
                ChatRequest(
                    messages=[ChatMessageItem(role="user", content="Agent Loop 是什么？")],
                    config_path=str(config),
                    vault_path=str(vault),
                    append_ledger=False,
                ),
                FakeServices(),  # type: ignore[arg-type]
            )

        planner_prompt = "\n".join(message.content for message in client.requests[0].messages)
        answer_prompt = "\n".join(message.content for message in client.requests[-1].messages)
        self.assertNotIn("Response style profile", planner_prompt)
        self.assertIn("Default answer depth: deep", answer_prompt)
        self.assertIn("latest user message explicitly asks", answer_prompt)
        self.assertEqual(response.stats["response_style"], "deep")

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

if __name__ == "__main__":
    unittest.main()
