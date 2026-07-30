from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest, ChatToolPlan
from knoarbor.core.schemas.image_generation import GeneratedImage, ImageGenerationResponse
from knoarbor.core.errors import ModelOutputError
from knoarbor.services.chat_agent import ChatAgentService, _direct_capability
from knoarbor.services.chat_tool_context import ChatToolContext
from knoarbor.services.chat_tools import ChatToolExecutor
from knoarbor.storage.vault_layout import chat_artifacts_root
from tests.helpers.chat_fakes import (
    FakeChatClient,
    FakeChatKnowledge,
    FakeServices,
    chat_answer_fixture,
)


class ChatToolFlowTest(unittest.TestCase):
    def test_tool_context_does_not_carry_chat_session_state(self) -> None:
        self.assertNotIn("existing_session", ChatToolContext.__dataclass_fields__)

    def test_chat_registry_exposes_only_batch_retrieval(self) -> None:
        executor = ChatToolExecutor(
            request=ChatRequest(
                message=ChatMessageItem(role="user", content="问题"),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services=FakeServices(),  # type: ignore[arg-type]
        )

        self.assertTrue(executor.has_tool("retrieve_knowledge_batch"))
        self.assertFalse(executor.has_tool("search_knowledge"))
        self.assertFalse(executor.has_tool("read_evidence"))

    def test_image_capability_fails_when_provider_output_cannot_be_persisted(self) -> None:
        class EmptyImageGeneration:
            def is_available(self, config_path=None):
                return True

            def generate(self, request, *, config_path=None, provider_name=None):
                return ImageGenerationResponse(
                    provider="test",
                    model="image-test",
                    prompt=request.prompt,
                    images=[GeneratedImage()],
                )

        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            services.image_generation = EmptyImageGeneration()  # type: ignore[assignment]
            response = ChatAgentService(
                client_factory=lambda _request: FakeChatClient(
                    [
                        chat_answer_fixture(
                            answer="我会生成一张树的图片。",
                            generated_image_prompt="A green tree",
                        ),
                    ]
                )
            ).chat(
                ChatRequest(
                    message=ChatMessageItem(role="user", content="请生成一张树的图片"),
                    vault_path=tmp,
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )
            self.assertIn("optional_image_generation_failed", response.warnings)
            self.assertFalse(chat_artifacts_root(Path(tmp)).exists())

    def test_generated_image_trace_never_persists_provider_url(self) -> None:
        class SignedUrlImageGeneration:
            def is_available(self, config_path=None):
                return True

            def generate(self, request, *, config_path=None, provider_name=None):
                return ImageGenerationResponse(
                    provider="test",
                    model="image-test",
                    prompt=request.prompt,
                    images=[
                        GeneratedImage(
                            url="https://provider.invalid/image.png?secret=signed-token",
                            b64_json="ZmFrZS1wbmc=",
                            mime_type="image/png",
                        )
                    ],
                )

        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            services.image_generation = SignedUrlImageGeneration()  # type: ignore[assignment]
            response = ChatAgentService(
                client_factory=lambda _request: FakeChatClient(
                    [
                        chat_answer_fixture(
                            answer="我会生成一张树的图片。",
                            generated_image_prompt="A green tree",
                        ),
                    ]
                )
            ).chat(
                ChatRequest(
                    message=ChatMessageItem(role="user", content="请生成一张树的图片"),
                    vault_path=tmp,
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )

        self.assertNotIn("signed-token", response.model_dump_json())
        self.assertNotIn("original_src", response.model_dump_json())

    def test_image_intent_never_bypasses_answer_decision_and_composer(self) -> None:
        for request in ("请生成一张绿色树形知识图谱图片", "画一幅山水图", "create an image of a tree"):
            with self.subTest(request=request):
                self.assertIsNone(_direct_capability(request))
        for question in ("如何生成图片？", "为什么不能生成图片？", "how does image generation work?"):
            with self.subTest(question=question):
                self.assertIsNone(_direct_capability(question))

    def test_model_routed_generated_image_is_labeled_and_counts_usage(self) -> None:
        services = FakeServices()
        with tempfile.TemporaryDirectory() as tmp:
            response = ChatAgentService(
                client_factory=lambda _request: FakeChatClient(
                    [
                        chat_answer_fixture(
                            answer="已按要求创建图片。",
                            generated_image_prompt="A green sapling",
                        ),
                    ]
                )
            ).chat(
                ChatRequest(
                    message=ChatMessageItem(role="user", content="请生成一张绿色树苗图片"),
                    vault_path=tmp,
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )

        self.assertIn("本轮生成图片", response.answer)
        self.assertEqual(response.stats["total_tokens"], 46)

    def test_image_tool_is_absent_when_provider_capability_is_unavailable(self) -> None:
        services = FakeServices()
        services.image_generation.available = False
        executor = ChatToolExecutor(
            request=ChatRequest(
                message=ChatMessageItem(role="user", content="请画一棵树"),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services=services,  # type: ignore[arg-type]
        )

        self.assertFalse(executor.has_tool("generate_image"))
        trace = executor.execute(
            ChatToolPlan(tool_calls=[{"name": "generate_image", "arguments": {"prompt": "tree"}}]),
            "请画一棵树",
        )
        self.assertEqual(trace[0].status, "error")
        self.assertIn("Unknown Chat tool", trace[0].summary)

    def test_answer_decision_can_request_one_auxiliary_image(self) -> None:
        client = FakeChatClient(
            [
                chat_answer_fixture(
                    answer="Agent Loop 是推理、行动和观察的循环。",
                    spans=["sp_1_1"],
                    generated_image_prompt=("A concise cycle diagram of reasoning, action, and observation"),
                ),
            ]
        )
        services = FakeServices()
        with tempfile.TemporaryDirectory() as tmp:
            response = ChatAgentService(client_factory=lambda _request: client).chat(
                ChatRequest(
                    message=ChatMessageItem(role="user", content="解释 Agent Loop，最好用图辅助"),
                    vault_path=tmp,
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(
            [item.tool for item in response.tool_trace],
            [
                "retrieve_knowledge_batch",
                "generate_image",
            ],
        )
        self.assertIn("![Generated image 1]", response.answer)
        self.assertIn("本轮生成图片（非知识库证据）", response.answer)
        self.assertEqual(len(services.image_generation.requests), 1)
        self.assertEqual(response.stats["total_tokens"], 46)
        answer_state = client.requests[-2].messages[-1].content
        self.assertIn(
            '"runtime_capabilities": {"generate_image": true}',
            answer_state,
        )
        composer_state = client.requests[-1].messages[-1].content
        self.assertIn('"visual_ref": "generated_visual_1"', composer_state)
        self.assertIn(
            '"description": "A concise cycle diagram of reasoning, action, and observation"',
            composer_state,
        )
        for private_field in (
            "stored_path",
            "manifest_path",
            "vault-assets",
            "![Generated image",
        ):
            self.assertNotIn(private_field, composer_state)

    def test_explicit_source_image_request_cannot_be_replaced_by_generation(
        self,
    ) -> None:
        client = FakeChatClient(
            [
                chat_answer_fixture(
                    answer="Agent Loop 是推理、行动和观察的循环。",
                    spans=["sp_1_1"],
                    gap="匹配的文档原图",
                    gap_markdown="当前证据没有提供匹配的文档原图。",
                ),
            ]
        )
        services = FakeServices()
        with tempfile.TemporaryDirectory() as tmp:
            response = ChatAgentService(client_factory=lambda _request: client).chat(
                ChatRequest(
                    message=ChatMessageItem(
                        role="user",
                        content="展示文档原图，并解释 Agent Loop。",
                    ),
                    vault_path=tmp,
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(
            [item.tool for item in response.tool_trace],
            ["retrieve_knowledge_batch"],
        )
        self.assertEqual(services.image_generation.requests, [])
        decision_state = client.requests[-2].messages[-1].content
        composer_state = client.requests[-1].messages[-1].content
        self.assertIn(
            '"runtime_capabilities": {"generate_image": true}',
            decision_state,
        )
        self.assertIn(
            '"generated_image": {"status": "not_requested", "visuals": []}',
            composer_state,
        )
        self.assertNotIn("source_attachments_requested", composer_state)

    def test_requested_source_attachment_is_rendered_from_selected_raw(
        self,
    ) -> None:
        class SourceImageKnowledge(FakeChatKnowledge):
            def read_evidence(self, context, arguments):
                observation = super().read_evidence(context, arguments)
                observation.result["raw_evidence"][0]["attachments"] = [
                    {
                        "attachment_id": "att:agent-loop",
                        "attachment_type": "image",
                        "topic": "Agent Loop",
                        "markdown_src": "![Agent Loop](/vault-assets/agent-loop.png)",
                    }
                ]
                return observation

        client = FakeChatClient(
            [
                chat_answer_fixture(
                    answer="Agent Loop 是推理、行动和观察的循环。",
                    spans=["sp_1_1"],
                    visuals=["visual_1_1"],
                ),
            ]
        )
        services = FakeServices()
        services.chat_knowledge = SourceImageKnowledge()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                message=ChatMessageItem(
                    role="user",
                    content="展示文档原图，并解释 Agent Loop。",
                ),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services,  # type: ignore[arg-type]
        )

        self.assertIn(
            "![Agent Loop](/vault-assets/agent-loop.png)",
            response.answer,
        )
        self.assertEqual(services.image_generation.requests, [])

    def test_composer_renders_selected_raw_attachment_without_keyword_gate(
        self,
    ) -> None:
        class SourceImageKnowledge(FakeChatKnowledge):
            def read_evidence(self, context, arguments):
                observation = super().read_evidence(context, arguments)
                observation.result["raw_evidence"][0]["attachments"] = [
                    {
                        "attachment_id": "att:agent-loop",
                        "attachment_type": "image",
                        "topic": "Agent Loop",
                        "description": "Cycle of reasoning, action, and observation.",
                        "markdown_src": "![Agent Loop](/vault-assets/agent-loop.png)",
                    }
                ]
                return observation

        client = FakeChatClient(
            [
                chat_answer_fixture(
                    answer="Agent Loop 是推理、行动和观察的循环。",
                    spans=["sp_1_1"],
                    visuals=["visual_1_1"],
                ),
            ]
        )
        services = FakeServices()
        services.chat_knowledge = SourceImageKnowledge()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                message=ChatMessageItem(
                    role="user",
                    content="解释 Agent Loop 的工作方式。",
                ),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services,  # type: ignore[arg-type]
        )

        answer_state = client.requests[-1].messages[-1].content
        self.assertNotIn('"attachment_id": "att:agent-loop"', answer_state)
        self.assertIn('"visual_ref": "visual_1_1"', answer_state)
        self.assertIn(
            "![Agent Loop](/vault-assets/agent-loop.png)",
            response.answer,
        )

    def test_optional_image_failure_preserves_grounded_text_answer(self) -> None:
        class FailingImageGeneration:
            def is_available(self, config_path=None):
                return True

            def generate(self, request, *, config_path=None, provider_name=None):
                raise RuntimeError("image provider offline")

        client = FakeChatClient(
            [
                chat_answer_fixture(
                    answer="Agent Loop 是推理、行动和观察的循环。",
                    spans=["sp_1_1"],
                    generated_image_prompt="Agent Loop cycle diagram",
                ),
            ]
        )
        services = FakeServices()
        services.image_generation = FailingImageGeneration()  # type: ignore[assignment]
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                message=ChatMessageItem(role="user", content="解释 Agent Loop，最好用图辅助"),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services,  # type: ignore[arg-type]
        )

        self.assertIn("Agent Loop 是推理、行动和观察的循环", response.answer)
        self.assertNotIn("![Generated image", response.answer)
        self.assertEqual(response.tool_trace[-1].tool, "generate_image")
        self.assertEqual(response.tool_trace[-1].status, "error")
        self.assertIn("optional_image_generation_failed", response.warnings)
        composer_state = client.requests[-1].messages[-1].content
        self.assertIn(
            '"generated_image": {"status": "failed", "visuals": []}',
            composer_state,
        )

    def test_general_mode_can_request_one_auxiliary_image(self) -> None:
        client = FakeChatClient(
            [
                {"selected_region_ids": []},
                chat_answer_fixture(
                    answer="这里是一段场景说明。",
                    generated_image_prompt="A calm mountain landscape at sunrise",
                ),
            ]
        )
        services = FakeServices()
        services.chat_knowledge.query_status = "no_match"
        with tempfile.TemporaryDirectory() as tmp:
            response = ChatAgentService(
                client_factory=lambda _request: client,
            ).chat(
                ChatRequest(
                    message=ChatMessageItem(role="user", content="描述一个适合做插画的日出山景"),
                    vault_path=tmp,
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(response.answer_provenance.mode, "general_knowledge")
        self.assertEqual(response.tool_trace[-1].tool, "generate_image")
        self.assertIn("![Generated image 1]", response.answer)
        general_state = client.requests[-1].messages[-1].content
        self.assertIn(
            '"generated_image": {"status": "available"',
            general_state,
        )
        self.assertIn('"conversation_context": []', general_state)
        self.assertNotIn("bounded_conversation_turns", general_state)

    def test_unavailable_image_capability_is_not_advertised_to_decision(self) -> None:
        client = FakeChatClient(
            [
                {"selected_region_ids": []},
                chat_answer_fixture(answer="纯文本回答。"),
            ]
        )
        services = FakeServices()
        services.chat_knowledge.query_status = "no_match"
        services.image_generation.available = False
        response = ChatAgentService(
            client_factory=lambda _request: client,
        ).chat(
            ChatRequest(
                message=ChatMessageItem(role="user", content="解释一个知识库之外的普通概念"),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(response.answer, "纯文本回答。")
        self.assertNotIn("generate_image", [item.tool for item in response.tool_trace])
        general_state = client.requests[-1].messages[-1].content
        self.assertIn(
            '"generated_image": {"status": "not_requested", "visuals": []}',
            general_state,
        )

    def test_general_mode_rejects_image_proposal_when_capability_is_unavailable(self) -> None:
        client = FakeChatClient(
            [
                {"selected_region_ids": []},
                {
                    "mode": "general",
                    "spans": [],
                    "visuals": [],
                    "gap": None,
                    "generated_image_prompt": "Draw a simple illustration.",
                },
            ]
        )
        services = FakeServices()
        services.chat_knowledge.query_status = "no_match"
        services.image_generation.available = False
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            vault.mkdir()
            config = root / "config.yaml"
            config.write_text(
                f"""
vault:
  path: {vault}
models:
  retry:
    enabled: true
    max_attempts: 1
    backoff_seconds: 0
    retry_on_invalid_output: true
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ModelOutputError, "unavailable image generation"):
                ChatAgentService(
                    client_factory=lambda _request: client,
                ).chat(
                    ChatRequest(
                        message=ChatMessageItem(role="user", content="解释一个知识库之外的普通概念"),
                        config_path=str(config),
                        vault_path=str(vault),
                        append_ledger=False,
                    ),
                    services,  # type: ignore[arg-type]
                )

    def test_candidate_retrieval_can_resolve_to_general(self) -> None:
        client = FakeChatClient(
            [
                chat_answer_fixture(answer="Alpha 和 Beta 的通用解释。"),
            ]
        )

        services = FakeServices()
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                message=ChatMessageItem(role="user", content="Alpha 和 Beta 分别如何工作？"),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(response.answer, "Alpha 和 Beta 的通用解释。")
        self.assertEqual(response.answer_provenance.mode, "general_knowledge")
        self.assertEqual(
            response.answer_provenance.chat_outcome,
            "planning_exhausted",
        )
        self.assertEqual(response.citations, [])
        self.assertEqual(response.stats["model_calls"], 3)
        self.assertEqual(
            [item["query"] for item in response.stats["retrieval_batch"]["query_expressions"]],
            ["Alpha 和 Beta 分别如何工作？"],
        )
        navigator_states = [
            request.messages[-1].content for request in client.requests if "retrieval planner" in request.messages[0].content.lower()
        ]
        self.assertEqual(len(navigator_states), 1)
        self.assertEqual(len(client.requests), 3)

    def test_vault_inventory_is_direct_capability(self) -> None:
        response = ChatAgentService(client_factory=lambda _request: FakeChatClient([])).chat(
            ChatRequest(
                message=ChatMessageItem(role="user", content="有哪些知识库？"),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            FakeServices(),  # type: ignore[arg-type]
        )
        self.assertEqual(response.answer_provenance.mode, "direct_capability")
        self.assertEqual([item.tool for item in response.tool_trace], ["list_vaults"])
        self.assertIn("Agent Engineering", response.answer)
        self.assertIn("RAG Notes", response.answer)

    def test_ui_word_does_not_bypass_factual_retrieval(self) -> None:
        client = FakeChatClient(
            [
                chat_answer_fixture(
                    answer="Agent Loop 是推理、行动和观察的循环。",
                    spans=["sp_1_1"],
                ),
            ]
        )
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            ChatRequest(
                message=ChatMessageItem(role="user", content="删除按钮为什么这样设计？"),
                vault_path="/tmp/vault",
                append_ledger=False,
            ),
            FakeServices(),  # type: ignore[arg-type]
        )
        self.assertEqual(response.answer_provenance.mode, "knowledge_grounded")
        self.assertEqual([item.tool for item in response.tool_trace], ["retrieve_knowledge_batch"])

    def test_multi_vault_scope_keeps_general_mode_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "vault-a").mkdir()
            (root / "vault-b").mkdir()
            config = root / "config.yaml"
            config.write_text(
                "config_version: 3\nvaults:\n  default: a\n  profiles:\n    a:\n      name: A\n      path: ./vault-a\n    b:\n      name: B\n      path: ./vault-b\n",
                encoding="utf-8",
            )
            services = FakeServices()
            services.chat_knowledge.query_status = "no_match"
            response = ChatAgentService(
                client_factory=lambda _request: FakeChatClient(
                    [
                        {
                            "selected_region_ids": [],
                        },
                        chat_answer_fixture(answer="通用回答。"),
                    ]
                )
            ).chat(
                ChatRequest(
                    message=ChatMessageItem(role="user", content="问题"),
                    config_path=str(config),
                    all_vaults=True,
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )
        self.assertEqual(response.answer_provenance.mode, "general_knowledge")
        self.assertEqual(response.stats["session_vault_id"], "all")


if __name__ == "__main__":
    unittest.main()
