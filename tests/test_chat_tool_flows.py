from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest
from knoarbor.services.chat_agent import ChatAgentService
from tests.helpers.chat_fakes import FakeChatClient, FakeServices


class ChatToolFlowTest(unittest.TestCase):
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
        self.assertEqual(response.tool_trace[0].result["returned_pages"], 2)
        self.assertEqual(response.tool_trace[0].result["pages"][0]["path"], "Agent-Loop.md")
        self.assertEqual(response.citations, [])
        self.assertEqual(response.hidden_evidence_count, 2)
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

    def test_generate_image_uses_provider_defaults_for_runtime_parameters(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [
                        {
                            "name": "generate_image",
                            "arguments": {
                                "prompt": "A clean product illustration",
                                "resolution": "1024x1024",
                                "num_inference_steps": 30,
                                "guidance": 7.5,
                            },
                        }
                    ],
                    "reason": "user asked to create an image",
                    "confidence": 0.9,
                },
                {"answer": "已生成图片。", "citations": []},
            ]
        )
        services = FakeServices()
        with tempfile.TemporaryDirectory() as tmp:
            response = ChatAgentService(client_factory=lambda _request: client).chat(
                ChatRequest(messages=[ChatMessageItem(role="user", content="生成一张产品说明图")], vault_path=tmp, append_ledger=False),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(response.tool_trace[0].tool, "generate_image")
        image_request = services.image_generation.requests[0]
        self.assertIsNone(image_request.resolution)
        self.assertIsNone(image_request.num_inference_steps)
        self.assertIsNone(image_request.guidance)

    def test_generate_image_persists_when_request_uses_vault_id(self) -> None:
        client = FakeChatClient(
            [
                {
                    "tool_calls": [{"name": "generate_image", "arguments": {"prompt": "A clean product illustration"}}],
                    "reason": "user asked to create an image",
                    "confidence": 0.9,
                },
                {"answer": "已生成图片。", "citations": []},
            ]
        )
        services = FakeServices()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            vault.mkdir()
            config = root / "config.yaml"
            config.write_text(
                f"""
project:
  name: Test
vault:
  path: {vault}
vaults:
  default: default
  profiles:
    default:
      name: Default
      path: {vault}
models:
  providers: {{}}
image_generation:
  providers: {{}}
""",
                encoding="utf-8",
            )

            response = ChatAgentService(client_factory=lambda _request: client).chat(
                ChatRequest(
                    messages=[ChatMessageItem(role="user", content="生成一张产品说明图")],
                    config_path=str(config),
                    vault_id="default",
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )

            image = response.tool_trace[0].result["images"][0]
            self.assertTrue(str(image["src"]).startswith("raw/derived/assets/images/generated/chat/"))
            self.assertIsNotNone(image["stored_path"])
            self.assertTrue(Path(str(image["stored_path"])).exists())
            self.assertEqual(Path(str(image["stored_path"])).read_bytes(), b"fake-png")

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
        self.assertEqual(services.wiki_pages.list_calls, 2)
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


if __name__ == "__main__":
    unittest.main()
