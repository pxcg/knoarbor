from __future__ import annotations

import json
import unittest
import tempfile
from unittest.mock import patch

from pydantic import ValidationError

from knoarbor.core.errors import ExternalServiceError, ModelOutputError
from knoarbor.core.schemas.chat import (
    ChatAnswerDecision,
    ChatCitation,
    ChatMessageItem,
    ChatRegionSearch,
    ChatRequest,
    ChatResponseComposerDraft,
    ChatRetrievalPlan,
    ChatToolTraceItem,
)
from knoarbor.services.chat_agent import (
    ChatAgentService,
    _direct_capability,
    _retrieval_search_directions,
)
from knoarbor.services.chat_answer import (
    validate_composer_markdown,
    with_citation_markers,
)
from knoarbor.services.chat_answer_decision import (
    ChatAnswerDecisionResult,
    _validate_and_project_decision,
)
from knoarbor.services.chat_evidence import (
    ChatEvidencePlanner,
)
from knoarbor.services.chat_model_call import _bounded_diagnostic_detail
from knoarbor.services.chat_response_composer import (
    ChatGeneratedImageState,
    ChatGeneratedVisual,
    ChatResponseComposer,
    _validate_and_finalize_composition,
)
from knoarbor.semantic.llm import ChatCompletionResponse
from knoarbor.runtime.local_operations import OperationCancellationToken
from knoarbor.runtime.run_monitor import RunCancelled
from tests.helpers.chat_fakes import FakeChatClient, FakeServices, chat_answer_fixture


def _request(content: str, *, include_trace: bool = True) -> ChatRequest:
    return ChatRequest(
        message=ChatMessageItem(role="user", content=content),
        vault_path="/tmp/vault",
        append_ledger=False,
        include_trace=include_trace,
    )


def _prepared_evidence(
    observations: list[ChatToolTraceItem],
):
    return ChatEvidencePlanner().prepare_answer_evidence(observations)


def _decision_result(
    observations: list[ChatToolTraceItem],
    payload: dict[str, object],
    evidence_ids: list[str],
    *,
    image_generation_available: bool = False,
) -> ChatAnswerDecisionResult:
    prepared = _prepared_evidence(observations)
    decision = ChatAnswerDecision.model_validate(payload)
    return ChatAnswerDecisionResult(
        decision=decision,
        materials=_validate_and_project_decision(
            decision,
            prepared,
            evidence_ids=evidence_ids,
            image_generation_available=image_generation_available,
        ),
        prepared_evidence=prepared,
        completion=ChatCompletionResponse(
            content="{}",
            provider="fake",
            model="fake",
        ),
        call_record={},
    )


def _grounded(answer: str = "Agent Loop 是循环 [1]。") -> dict[str, object]:
    return chat_answer_fixture(
        answer=answer.replace(" [1]", ""),
        spans=["sp_1_1"],
    )


class ChatAgentServiceTest(unittest.TestCase):
    def test_response_composer_contract_omits_unselected_visual_example(
        self,
    ) -> None:
        result = _decision_result(
            [],
            {
                "mode": "general",
                "spans": [],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": "Draw a concise diagram.",
            },
            [],
            image_generation_available=True,
        )

        state = json.loads(
            ChatResponseComposer()._composition_prompt(
                current_messages=[ChatMessageItem(role="user", content="请生成一张示意图。")],
                existing_session=None,
                decision_result=result,
                generated_image=ChatGeneratedImageState(
                    status="available",
                    visuals=(
                        ChatGeneratedVisual(
                            visual_ref="generated_visual_1",
                            description="A concise diagram.",
                            markdown="![Generated image 1](/generated.png)",
                        ),
                    ),
                ),
            )
        )

        self.assertEqual(
            [item["type"] for item in state["output_contract"]["items"]],
            ["text", "generated_visual", "text"],
        )
        self.assertEqual(
            state["output_contract"]["items"][0]["materials"],
            [],
        )
        self.assertIn(
            "source_visual items are forbidden",
            state["composition_checklist"][1],
        )
        self.assertIn(
            "Place every listed generated visual exactly once",
            state["composition_checklist"][2],
        )
        self.assertEqual(
            state["output_contract"]["items"][2]["materials"],
            [],
        )

    def test_response_composer_contract_includes_selected_visual_example(
        self,
    ) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:image",
                        "source_unit_id": "unit:image",
                        "content": "图示说明系统结构。",
                        "attachments": [
                            {
                                "topic": "系统结构",
                                "markdown_src": "![系统结构](/assets/figure.png)",
                            }
                        ],
                    }
                ],
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_1"],
                "visuals": ["visual_1_1"],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:image"],
        )

        state = json.loads(
            ChatResponseComposer()._composition_prompt(
                current_messages=[ChatMessageItem(role="user", content="展示文档原图。")],
                existing_session=None,
                decision_result=result,
            )
        )

        self.assertEqual(
            [item["type"] for item in state["output_contract"]["items"]],
            ["text", "source_visual"],
        )
        self.assertEqual(
            state["output_contract"]["items"][0]["materials"],
            ["material_1"],
        )
        self.assertEqual(
            state["output_contract"]["items"][1]["visual"],
            "visual_1_1",
        )
        self.assertIn(
            "do not move visuals to the end by default",
            state["composition_checklist"][1],
        )

    def test_response_composer_contract_interleaves_each_visual_with_its_owner_example(
        self,
    ) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:first",
                        "source_unit_id": "unit:first",
                        "content": "第一份材料说明第一张图。",
                        "attachments": [
                            {
                                "topic": "第一张图",
                                "markdown_src": "![第一张图](/assets/first.png)",
                            }
                        ],
                    },
                    {
                        "evidence_id": "ev:second",
                        "source_unit_id": "unit:second",
                        "content": "第二份材料说明第二张图。",
                        "attachments": [
                            {
                                "topic": "第二张图",
                                "markdown_src": "![第二张图](/assets/second.png)",
                            }
                        ],
                    },
                ],
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_1", "sp_2_1"],
                "visuals": ["visual_1_1", "visual_2_1"],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:first", "ev:second"],
        )

        state = json.loads(
            ChatResponseComposer()._composition_prompt(
                current_messages=[ChatMessageItem(role="user", content="分别说明两张图。")],
                existing_session=None,
                decision_result=result,
            )
        )

        self.assertEqual(
            state["output_contract"]["items"],
            [
                {
                    "type": "text",
                    "markdown": "natural answer Markdown explaining this material and its visuals",
                    "materials": ["material_1"],
                },
                {"type": "source_visual", "visual": "visual_1_1"},
                {
                    "type": "text",
                    "markdown": "natural answer Markdown explaining this material and its visuals",
                    "materials": ["material_2"],
                },
                {"type": "source_visual", "visual": "visual_2_1"},
            ],
        )

    def test_response_composer_contract_uses_gap_specific_shape(self) -> None:
        result = _decision_result(
            [],
            {
                "mode": "gap",
                "spans": [],
                "visuals": [],
                "gap": "所请求的本地资料",
                "generated_image_prompt": None,
            },
            [],
        )

        state = json.loads(
            ChatResponseComposer()._composition_prompt(
                current_messages=[ChatMessageItem(role="user", content="本地资料怎么说？")],
                existing_session=None,
                decision_result=result,
            )
        )

        self.assertEqual(state["output_contract"]["items"], [])
        self.assertEqual(
            state["output_contract"]["gap_markdown"],
            "required reader-facing limitation",
        )
        self.assertEqual(
            state["composition_checklist"][0],
            "Return no items and only the required gap_markdown.",
        )

    def test_retrieval_plan_rejects_unused_explanation_and_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            ChatRetrievalPlan.model_validate(
                {
                    "searches": [],
                    "reason": "unused",
                    "confidence": 0.9,
                }
            )

    def test_model_rejection_diagnostic_redacts_returned_field_value(self) -> None:
        error = ModelOutputError("field failed [type=extra_forbidden, " "input_value=private model text, input_type=str]")

        detail = _bounded_diagnostic_detail(error)

        self.assertIn("type=extra_forbidden", detail)
        self.assertIn("input_value=<redacted>", detail)
        self.assertNotIn("private model text", detail)

    def test_answer_decision_has_exact_small_model_contract(self) -> None:
        decision = ChatAnswerDecision.model_validate(
            {
                "mode": "general",
                "spans": [],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            }
        )

        self.assertEqual(
            set(decision.model_dump()),
            {"mode", "spans", "visuals", "gap", "generated_image_prompt"},
        )
        with self.assertRaises(ValidationError):
            ChatAnswerDecision.model_validate(
                {
                    **decision.model_dump(),
                    "reason": "not part of the handoff",
                }
            )

    def test_answer_decision_rejects_cross_raw_visual(self) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:text",
                        "source_unit_id": "unit:text",
                        "content": "第一段事实。",
                    },
                    {
                        "evidence_id": "ev:image",
                        "source_unit_id": "unit:image",
                        "content": "第二段事实。",
                        "attachments": [
                            {
                                "topic": "图示",
                                "markdown_src": "![图示](/assets/figure.png)",
                            }
                        ],
                    },
                ],
            },
        )
        decision = ChatAnswerDecision.model_validate(
            {
                "mode": "raw",
                "spans": ["sp_1_1"],
                "visuals": ["visual_2_1"],
                "gap": None,
                "generated_image_prompt": None,
            }
        )

        with self.assertRaisesRegex(ModelOutputError, "same Raw source"):
            _validate_and_project_decision(
                decision,
                _prepared_evidence([observation]),
                evidence_ids=["ev:text", "ev:image"],
                image_generation_available=False,
            )

    def test_response_composer_must_place_selected_visual_exactly_once(self) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:image",
                        "source_unit_id": "unit:image",
                        "content": "图示说明系统结构。",
                        "attachments": [
                            {
                                "topic": "系统结构",
                                "markdown_src": "![系统结构](/assets/figure.png)",
                            }
                        ],
                    }
                ],
            },
        )
        prepared = _prepared_evidence([observation])
        decision = ChatAnswerDecision.model_validate(
            {
                "mode": "raw",
                "spans": ["sp_1_1"],
                "visuals": ["visual_1_1"],
                "gap": None,
                "generated_image_prompt": None,
            }
        )
        result = ChatAnswerDecisionResult(
            decision=decision,
            materials=_validate_and_project_decision(
                decision,
                prepared,
                evidence_ids=["ev:image"],
                image_generation_available=False,
            ),
            prepared_evidence=prepared,
            completion=ChatCompletionResponse(
                content="{}",
                provider="fake",
                model="fake",
            ),
            call_record={},
        )
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "text",
                        "markdown": "系统结构如下。",
                        "materials": ["material_1"],
                    }
                ],
                "gap_markdown": None,
            }
        )

        with self.assertRaisesRegex(ModelOutputError, "exactly once"):
            _validate_and_finalize_composition(composer, result)

        misplaced = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "source_visual",
                        "visual": "visual_1_1",
                    },
                    {
                        "type": "text",
                        "markdown": "系统结构如下。",
                        "materials": ["material_1"],
                    },
                ],
                "gap_markdown": None,
            }
        )
        with self.assertRaisesRegex(ModelOutputError, "owning material"):
            _validate_and_finalize_composition(misplaced, result)

    def test_response_composer_allows_contiguous_visual_group_after_owner_text(
        self,
    ) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:image",
                        "source_unit_id": "unit:image",
                        "content": "两张图共同说明系统结构。",
                        "attachments": [
                            {
                                "topic": "系统结构一",
                                "markdown_src": "![系统结构一](/assets/figure-1.png)",
                            },
                            {
                                "topic": "系统结构二",
                                "markdown_src": "![系统结构二](/assets/figure-2.png)",
                            },
                        ],
                    }
                ],
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_1"],
                "visuals": ["visual_1_1", "visual_1_2"],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:image"],
        )
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "text",
                        "markdown": "两张系统结构图如下。",
                        "materials": ["material_1"],
                    },
                    {"type": "source_visual", "visual": "visual_1_1"},
                    {"type": "source_visual", "visual": "visual_1_2"},
                ],
                "gap_markdown": None,
            }
        )

        answer, _ = _validate_and_finalize_composition(composer, result)

        self.assertIn("figure-1.png", answer)
        self.assertIn("figure-2.png", answer)

    def test_response_composer_allows_visual_group_after_separate_owner_texts(
        self,
    ) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:first",
                        "source_unit_id": "unit:first",
                        "content": "第一份材料说明第一张图。",
                        "attachments": [
                            {
                                "topic": "第一张图",
                                "markdown_src": "![第一张图](/assets/first.png)",
                            }
                        ],
                    },
                    {
                        "evidence_id": "ev:second",
                        "source_unit_id": "unit:second",
                        "content": "第二份材料说明第二张图。",
                        "attachments": [
                            {
                                "topic": "第二张图",
                                "markdown_src": "![第二张图](/assets/second.png)",
                            }
                        ],
                    },
                ],
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_1", "sp_2_1"],
                "visuals": ["visual_1_1", "visual_2_1"],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:first", "ev:second"],
        )
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "text",
                        "markdown": "第一份材料的说明。",
                        "materials": ["material_1"],
                    },
                    {
                        "type": "text",
                        "markdown": "第二份材料的说明。",
                        "materials": ["material_2"],
                    },
                    {"type": "source_visual", "visual": "visual_1_1"},
                    {"type": "source_visual", "visual": "visual_2_1"},
                ],
                "gap_markdown": None,
            }
        )

        answer, _ = _validate_and_finalize_composition(composer, result)

        self.assertIn("first.png", answer)
        self.assertIn("second.png", answer)

    def test_response_composer_rejects_projected_material_id_in_prose(self) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:text",
                        "source_unit_id": "unit:text",
                        "content": "材料说明了系统结构。",
                    }
                ],
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_1"],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:text"],
        )
        material_id = result.materials[0].material_id
        self.assertEqual(material_id, "material_1")
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "text",
                        "markdown": f"来源：{material_id}",
                        "materials": [material_id],
                    }
                ],
                "gap_markdown": None,
            }
        )

        with self.assertRaisesRegex(ModelOutputError, "request-local"):
            _validate_and_finalize_composition(composer, result)

    def test_response_composer_still_rejects_invented_transport_id(self) -> None:
        result = _decision_result(
            [
                ChatToolTraceItem(
                    tool="retrieve_knowledge_batch",
                    result={
                        "raw_evidence": [
                            {
                                "evidence_id": "ev:text",
                                "source_unit_id": "unit:text",
                                "content": "材料说明了系统结构。",
                            }
                        ],
                    },
                )
            ],
            {
                "mode": "raw",
                "spans": ["sp_1_1"],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:text"],
        )
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "text",
                        "markdown": "来源：material_999",
                        "materials": ["material_1"],
                    }
                ],
                "gap_markdown": None,
            }
        )

        with self.assertRaisesRegex(ModelOutputError, "request-local"):
            _validate_and_finalize_composition(composer, result)

    def test_response_composer_allows_ordinary_technical_underscore_terms(
        self,
    ) -> None:
        result = _decision_result(
            [],
            {
                "mode": "general",
                "spans": [],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            },
            [],
        )
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "text",
                        "markdown": ("`unit_test`、`material_design`、`evidence_based` 和 " "`visual_effect` 都是普通技术词。"),
                        "materials": [],
                    }
                ],
                "gap_markdown": None,
            }
        )

        answer, citations = _validate_and_finalize_composition(composer, result)

        self.assertIn("material_design", answer)
        self.assertEqual(citations, [])

    def test_composer_material_exposes_source_label_and_source_order(self) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:text",
                        "source_unit_id": "unit:text",
                        "document_title": "来源文档",
                        "title": "来源标题",
                        "content": "第一句。第二句。",
                    }
                ],
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_2", "sp_1_1"],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:text"],
        )

        self.assertEqual(
            result.materials[0].model_payload(),
            {
                "material_id": "material_1",
                "source_label": "来源文档 — 来源标题",
                "raw": ["第一句。", "第二句。"],
                "visuals": [],
            },
        )

    def test_response_composer_allows_natural_markdown_in_one_material_item(
        self,
    ) -> None:
        result = _decision_result(
            [
                ChatToolTraceItem(
                    tool="retrieve_knowledge_batch",
                    result={
                        "raw_evidence": [
                            {
                                "evidence_id": "ev:text",
                                "source_unit_id": "unit:text",
                                "content": "第一项。第二项。",
                            }
                        ],
                    },
                )
            ],
            {
                "mode": "raw",
                "spans": ["sp_1_1", "sp_1_2"],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:text"],
        )
        valid_shapes = [
            "第一段。\n\n第二段。",
            "说明文字\n- 第一项\n- 第二项",
            "说明文字\n| A | B |\n|---|---|\n| 1 | 2 |",
            "# 标题\n说明文字\n| A | B |\n|---|---|\n| 1 | 2 |",
            "# 标题\n## 子标题\n说明文字",
            "```python\nvalues = [1]\n```",
        ]
        for markdown in valid_shapes:
            with self.subTest(markdown=markdown):
                composer = ChatResponseComposerDraft.model_validate(
                    {
                        "items": [
                            {
                                "type": "text",
                                "markdown": markdown,
                                "materials": ["material_1"],
                            }
                        ],
                        "gap_markdown": None,
                    }
                )
                answer, citations = _validate_and_finalize_composition(
                    composer,
                    result,
                )
                uncited = answer[:-5] if answer.endswith("\n\n[1]") else answer.replace(" [1]。", "。").replace(" [1]", "")
                self.assertEqual(
                    uncited,
                    markdown,
                )
                self.assertEqual(len(citations), 1)

    def test_composer_markdown_rejects_only_citation_like_numeric_markers(
        self,
    ) -> None:
        for markdown in (
            "数组索引 values[1] 是有效内容。",
            "行内代码 `[1]` 是有效内容。",
            "```python\nvalues = [1]\n```",
            "```markdown\n![example](/example.png)\n```",
            "```python\nmaterial_1 = load()\n```",
            "示例写法是 `![alt](url)`。",
            "接口路径是 /api/v1/users。",
            "工具路径是 C:\\Tools\\runner.exe。",
        ):
            with self.subTest(markdown=markdown):
                validate_composer_markdown(markdown)

        for markdown in ("回答 [1]", "回答（[1]）", "[12] 是伪造引用"):
            with self.subTest(markdown=markdown):
                with self.assertRaisesRegex(ModelOutputError, "citation markers"):
                    validate_composer_markdown(markdown)

    def test_table_citation_is_rendered_after_the_table(self) -> None:
        markdown = "| 来源 | 内容 |\n|---|---|\n| A | B |"

        rendered = with_citation_markers(markdown, [1])

        self.assertEqual(
            rendered,
            "| 来源 | 内容 |\n|---|---|\n| A | B |\n\n[1]",
        )

    def test_generated_image_prompt_rejects_transport_and_image_syntax(
        self,
    ) -> None:
        for prompt in (
            "Draw material_1 as a diagram",
            "![source](/private/tmp/source.png)",
        ):
            with self.subTest(prompt=prompt):
                with self.assertRaises(ModelOutputError):
                    _decision_result(
                        [],
                        {
                            "mode": "general",
                            "spans": [],
                            "visuals": [],
                            "gap": None,
                            "generated_image_prompt": prompt,
                        },
                        [],
                        image_generation_available=True,
                    )

        allowed = _decision_result(
            [],
            {
                "mode": "general",
                "spans": [],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": ("Draw a technical diagram of the /api/v1/users route"),
            },
            [],
            image_generation_available=True,
        )
        self.assertEqual(
            allowed.decision.generated_image_prompt,
            "Draw a technical diagram of the /api/v1/users route",
        )

    def test_response_composer_places_generated_visual_exactly_once(self) -> None:
        result = _decision_result(
            [],
            {
                "mode": "general",
                "spans": [],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": "Draw a technical diagram.",
            },
            [],
            image_generation_available=True,
        )
        generated = ChatGeneratedImageState(
            status="available",
            visuals=(
                ChatGeneratedVisual(
                    visual_ref="generated_visual_1",
                    description="A technical diagram",
                    markdown=("**本轮生成图片（非知识库证据）**\n\n" "![Generated image 1](/generated.png)"),
                ),
            ),
        )
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "generated_visual",
                        "visual": "generated_visual_1",
                    },
                    {
                        "type": "text",
                        "markdown": "这里是说明。",
                        "materials": [],
                    },
                ],
                "gap_markdown": None,
            }
        )
        answer, _ = _validate_and_finalize_composition(
            composer,
            result,
            generated,
        )
        self.assertLess(answer.index("Generated image 1"), answer.index("这里是说明"))

        missing = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "text",
                        "markdown": "这里是说明。",
                        "materials": [],
                    }
                ],
                "gap_markdown": None,
            }
        )
        with self.assertRaisesRegex(ModelOutputError, "generated visual exactly once"):
            _validate_and_finalize_composition(missing, result, generated)

    def test_response_composer_leaves_decided_gap_wording_to_model(self) -> None:
        result = _decision_result(
            [],
            {
                "mode": "gap",
                "spans": [],
                "visuals": [],
                "gap": "项目风险负责人",
                "generated_image_prompt": None,
            },
            [],
        )
        for gap_markdown in (
            "## 项目风险负责人",
            "**项目风险负责人**",
            "`项目风险负责人`",
        ):
            with self.subTest(gap_markdown=gap_markdown):
                composer = ChatResponseComposerDraft.model_validate(
                    {
                        "items": [],
                        "gap_markdown": gap_markdown,
                    }
                )

                answer, citations = _validate_and_finalize_composition(
                    composer,
                    result,
                )
                self.assertEqual(answer, gap_markdown)
                self.assertEqual(citations, [])

    def test_general_response_can_include_an_unsupported_remainder(self) -> None:
        result = _decision_result(
            [],
            {
                "mode": "general",
                "spans": [],
                "visuals": [],
                "gap": "今天的实时价格",
                "generated_image_prompt": None,
            },
            [],
        )
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "text",
                        "markdown": "我可以说明这个产品的稳定概念。",
                        "materials": [],
                    }
                ],
                "gap_markdown": "但这里无法确认今天的实时价格。",
            }
        )

        answer, citations = _validate_and_finalize_composition(composer, result)

        self.assertIn("稳定概念", answer)
        self.assertIn("实时价格", answer)
        self.assertEqual(citations, [])

    def test_gap_response_can_keep_explicit_generated_image_authorization(
        self,
    ) -> None:
        result = _decision_result(
            [],
            {
                "mode": "gap",
                "spans": [],
                "visuals": [],
                "gap": "知识库没有提供该结构",
                "generated_image_prompt": "Draw a conceptual structure diagram.",
            },
            [],
            image_generation_available=True,
        )
        composer = ChatResponseComposerDraft.model_validate(
            {
                "items": [
                    {
                        "type": "generated_visual",
                        "visual": "generated_visual_1",
                    }
                ],
                "gap_markdown": "知识库没有提供该结构。",
            }
        )

        generated = ChatGeneratedImageState(
            status="available",
            visuals=(
                ChatGeneratedVisual(
                    visual_ref="generated_visual_1",
                    description="A conceptual structure diagram",
                    markdown="![Generated image 1](/generated.png)",
                ),
            ),
        )
        answer, citations = _validate_and_finalize_composition(
            composer,
            result,
            generated,
        )

        self.assertIn("Generated image 1", answer)
        self.assertIn("知识库没有提供该结构。", answer)
        self.assertEqual(citations, [])
        state = ChatResponseComposer()._composition_prompt(
            current_messages=[ChatMessageItem(role="user", content="画图，但只使用知识库事实。")],
            existing_session=None,
            decision_result=result,
            generated_image=generated,
        )
        self.assertIn("Return no factual text or source_visual items", state)
        self.assertNotIn("Return no items and only", state)

    def test_response_composer_receives_latest_question_and_history(self) -> None:
        client = FakeChatClient(
            [
                {
                    "mode": "general",
                    "spans": [],
                    "visuals": [],
                    "gap": None,
                    "generated_image_prompt": None,
                },
                {
                    "items": [
                        {
                            "type": "text",
                            "markdown": "已按表格要求整理。",
                            "materials": [],
                        }
                    ],
                    "gap_markdown": None,
                },
            ]
        )
        response = ChatAgentService(client_factory=lambda _request: client).chat(_request("把它整理成表格"), FakeServices())  # type: ignore[arg-type]

        self.assertEqual(response.answer, "已按表格要求整理。")
        composition_state = __import__("json").loads(client.requests[-1].messages[-1].content)["composition_state"]
        self.assertEqual(
            composition_state["latest_user_message"],
            "把它整理成表格",
        )
        self.assertIn("conversation_context", composition_state)
        self.assertEqual(
            [message.role for message in client.requests[-1].messages],
            ["system", "user"],
        )

    def test_v4_contract_rejects_removed_policy_and_v3_schema(self) -> None:
        payload = {
            "schema_version": "chat_request.v3",
            "answer_policy": "knowledge_then_general",
            "message": {"role": "user", "content": "问题"},
            "vault_path": "/tmp/vault",
        }

        with self.assertRaises(ValidationError):
            ChatRequest.model_validate(payload)

        request = _request("问题")
        self.assertEqual(request.schema_version, "chat_request.v4")
        self.assertNotIn("answer_policy", request.model_dump())

    def test_retrieval_resource_exhaustion_returns_typed_non_resumable_gap(self) -> None:
        services = FakeServices()
        services.chat_knowledge.query_status = "resource_exhausted"

        response = ChatAgentService(client_factory=lambda _request: FakeChatClient([])).chat(  # type: ignore[arg-type]
            _request("Agent Loop 是什么？"),
            services,
        )

        self.assertEqual(response.answer_provenance.query_outcome, "resource_exhausted")
        self.assertEqual(response.answer_provenance.chat_outcome, "resource_exhausted")
        self.assertEqual(response.answer_provenance.mode, "knowledge_gap")
        self.assertEqual(response.citations, [])
        self.assertIn("不代表知识库中没有相关内容", response.answer)

    def test_index_unavailable_stays_typed_and_never_routes_to_general(self) -> None:
        services = FakeServices()
        services.chat_knowledge.query_status = "index_unavailable"

        response = ChatAgentService(client_factory=lambda _request: FakeChatClient([])).chat(  # type: ignore[arg-type]
            _request("Agent Loop 是什么？"),
            services,
        )

        self.assertEqual(response.answer_provenance.query_outcome, "index_unavailable")
        self.assertEqual(response.answer_provenance.chat_outcome, "tool_error")
        self.assertEqual(response.answer_provenance.mode, "knowledge_gap")
        self.assertIn("未转入通用知识回答", response.answer)

    def test_fast_unified_recall_reads_raw_then_runs_answer_pipeline(self) -> None:
        client = FakeChatClient([_grounded()])
        response = ChatAgentService(client_factory=lambda _request: client).chat(_request("Agent Loop 是什么？"), FakeServices())  # type: ignore[arg-type]

        self.assertEqual([item.tool for item in response.tool_trace], ["retrieve_knowledge_batch"])
        self.assertEqual(response.stats["model_calls"], 3)
        self.assertEqual(response.answer_provenance.mode, "knowledge_grounded")
        self.assertEqual(response.answer_provenance.query_outcome, "candidates")
        self.assertEqual(response.citations[0].evidence_id, "ev:test")
        self.assertEqual(response.citations[0].char_start, 100)
        self.assertEqual(response.citations[0].char_end, 100 + len("Agent Loop 是推理、行动和观察的循环。"))
        source_index = next(index for index, event in enumerate(response.events) if event.event_type == "answer_source_selected")
        model_index = next(
            index
            for index, event in enumerate(response.events)
            if event.event_type == "model_call_started" and event.payload.get("semantic_phase") == "response_composer"
        )
        self.assertGreater(source_index, model_index)
        self.assertEqual(response.events[source_index].payload["source_path"], "local_knowledge")
        self.assertFalse(response.events[source_index].payload["provisional"])
        decision_prompt = client.requests[-2].messages[-1].content
        composer_prompt = client.requests[-1].messages[-1].content
        self.assertIn('"kind": "query_raw_evidence"', decision_prompt)
        self.assertIn('"support_span_id": "sp_1_1"', decision_prompt)
        self.assertIn(
            "omit only clearly unrelated visuals",
            decision_prompt,
        )
        self.assertIn(
            "do not require a relevant visual to outperform text",
            decision_prompt,
        )
        self.assertNotIn("materially clearer than text alone", decision_prompt)
        self.assertIn('"material_id": "material_1"', composer_prompt)
        self.assertNotIn('"support_span_id"', composer_prompt)
        self.assertNotIn("support_span_authorization", decision_prompt)
        self.assertNotIn("Agent loop control patterns.", decision_prompt)
        self.assertNotIn("/tmp/vault", "\n".join(message.content for message in client.requests[-1].messages))
        navigator_prompt = client.requests[0].messages[-1].content
        self.assertNotIn('"candidate_ids"', navigator_prompt)
        self.assertNotIn('"query_outcomes"', navigator_prompt)

    def test_navigator_reads_corpus_outline_and_scopes_literal_query(self) -> None:
        catalog = {
            "schema_version": "active_corpus_outline.v1",
            "authority": "query_locator_only",
            "vaults": [
                {
                    "vault_id": "test",
                    "vault_name": "Test",
                    "documents": [
                        {
                            "region_id": "region_doc",
                            "title": "MinerU 使用指南",
                            "source_name": "mineru.pdf",
                            "source_type": "pdf",
                            "sections": [
                                {
                                    "region_id": "region_mineru_images",
                                    "title": "图片提取",
                                }
                            ],
                        }
                    ],
                }
            ],
            "document_count": 1,
            "region_count": 2,
            "unavailable_vault_ids": [],
        }
        client = FakeChatClient(
            [
                {
                    "selected_region_ids": ["region_mineru_images"],
                },
                _grounded(),
            ]
        )
        with patch(
            "knoarbor.services.chat_agent.build_active_corpus_catalog",
            return_value=catalog,
        ):
            response = ChatAgentService(client_factory=lambda _request: client).chat(
                _request("解析器如何理解图片？"),
                FakeServices(),  # type: ignore[arg-type]
            )

        planning_payload = __import__("json").loads(client.requests[0].messages[-1].content)
        self.assertEqual(set(planning_payload), {"planning_state"})
        planning_state = planning_payload["planning_state"]
        self.assertEqual(planning_state["active_corpus_outline"], catalog)
        self.assertEqual(
            response.stats["retrieval_batch"]["query_expressions"],
            [
                {
                    "query_id": "q1",
                    "query": "解析器如何理解图片？",
                    "region_id": "region_mineru_images",
                    "group_id": "region:region_mineru_images",
                }
            ],
        )
        self.assertEqual(
            [item.tool for item in response.tool_trace],
            ["retrieve_knowledge_batch"],
        )

    def test_navigation_can_select_multiple_document_sections_without_rewrite(self) -> None:
        catalog = {
            "schema_version": "active_corpus_outline.v1",
            "authority": "query_locator_only",
            "vaults": [
                {
                    "vault_id": "test",
                    "vault_name": "Test",
                    "documents": [
                        {
                            "region_id": "region_who",
                            "title": "WHO mortality report",
                            "source_name": "who.pdf",
                            "source_type": "pdf",
                            "sections": [
                                {"region_id": "region_maternal", "title": "Maternal mortality"},
                                {"region_id": "region_child", "title": "Child mortality"},
                            ],
                        }
                    ],
                }
            ],
            "document_count": 1,
            "region_count": 3,
        }
        client = FakeChatClient(
            [
                {
                    "selected_region_ids": ["region_maternal", "region_child"],
                },
                _grounded(),
            ]
        )
        with patch(
            "knoarbor.services.chat_agent.build_active_corpus_catalog",
            return_value=catalog,
        ):
            response = ChatAgentService(client_factory=lambda _request: client).chat(
                _request("WHO 报告如何概括孕产妇和儿童死亡变化？"),
                FakeServices(),  # type: ignore[arg-type]
            )

        self.assertEqual(
            [(item["query"], item["region_id"]) for item in response.stats["retrieval_batch"]["query_expressions"]],
            [
                ("WHO 报告如何概括孕产妇和儿童死亡变化？", "region_maternal"),
                ("WHO 报告如何概括孕产妇和儿童死亡变化？", "region_child"),
            ],
        )
        self.assertEqual(len(client.requests), 3)

    def test_navigator_failure_degrades_to_literal_only_batch(self) -> None:
        class NavigatorFailureClient(FakeChatClient):
            def complete(self, request):
                if "retrieval planner" in request.messages[0].content.lower():
                    self.requests.append(request)
                    raise ExternalServiceError("navigator unavailable")
                return super().complete(request)

        client = NavigatorFailureClient([_grounded()])
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            _request("Agent Loop 是什么？"),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(
            [item["query"] for item in response.stats["retrieval_batch"]["query_expressions"]],
            ["Agent Loop 是什么？"],
        )
        self.assertIn("retrieval_planner_unavailable", response.warnings)
        self.assertEqual(response.answer_provenance.mode, "knowledge_grounded")

    def test_query_evidence_reaches_answer_without_chat_side_reranking(self) -> None:
        services = FakeServices()
        read_arguments: list[dict[str, object]] = []

        def search(_context, arguments):
            candidates = [
                {"evidence_id": "ev:a1", "source_record_id": "source:a", "vault_id": "test", "score": 0.9},
                {"evidence_id": "ev:a2", "source_record_id": "source:a", "vault_id": "test", "score": 0.7},
                {"evidence_id": "ev:b1", "source_record_id": "source:b", "vault_id": "test", "score": 0.8},
                {"evidence_id": "ev:c1", "source_record_id": "source:c", "vault_id": "test", "score": 0.75},
            ]
            return ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                arguments=arguments,
                result={
                    "query": arguments["query"],
                    "query_outcomes": [
                        {
                            "vault_id": "test",
                            "status": "candidates",
                            "exhausted": True,
                            "channel_statuses": [
                                {"channel": "atom_claim", "status": "completed", "match_count": 32, "exhausted": True},
                                {"channel": "raw_lexical", "status": "completed", "match_count": 32, "exhausted": True},
                            ],
                        }
                    ],
                    "candidates": candidates,
                },
            )

        def read(_context, arguments):
            read_arguments.append(dict(arguments))
            evidence = [
                {
                    "evidence_id": evidence_id,
                    "raw_record_id": f"raw:{evidence_id}",
                    "raw_revision_id": f"rawrev:{evidence_id}",
                    "source_unit_id": f"unit:{evidence_id}",
                    "source_record_id": f"source:{evidence_id}",
                    "processing_record_id": f"processing:{evidence_id}",
                    "source_path": f"raw/{evidence_id}.md",
                    "unit_index": 0,
                    "unit_type": "section",
                    "title": evidence_id,
                    "content": ("Agent Loop 是推理、行动和观察的循环。" if evidence_id == "ev:a1" else f"{evidence_id} 的完整证据。"),
                }
                for evidence_id in arguments["evidence_ids"]
            ]
            return ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                arguments=arguments,
                citations=[
                    ChatCitation(kind="raw_evidence", evidence_id=item["evidence_id"], path=item["source_path"]) for item in evidence
                ],
                result={"raw_evidence": evidence},
            )

        services.chat_knowledge.search_knowledge = search  # type: ignore[method-assign]
        services.chat_knowledge.read_evidence = read  # type: ignore[method-assign]
        client = FakeChatClient([_grounded()])
        response = ChatAgentService(client_factory=lambda _request: client).chat(
            _request("Agent Loop 是什么？"),
            services,  # type: ignore[arg-type]
        )

        self.assertEqual(response.stats["retrieval_batch"]["candidate_count"], 4)
        self.assertEqual(
            [item["evidence_ids"] for item in read_arguments],
            [["ev:a1", "ev:a2", "ev:b1", "ev:c1"]],
        )
        decision_prompt = client.requests[-2].messages[-1].content
        composer_prompt = client.requests[-1].messages[-1].content
        self.assertIn('"support_span_id": "sp_1_1"', decision_prompt)
        self.assertIn('"support_span_id": "sp_2_1"', decision_prompt)
        self.assertIn('"support_span_id": "sp_3_1"', decision_prompt)
        self.assertIn('"support_span_id": "sp_4_1"', decision_prompt)
        self.assertNotIn('"evidence_id"', decision_prompt)
        self.assertNotIn('"support_span_id"', composer_prompt)
        self.assertIn('"material_id": "material_1"', composer_prompt)
        self.assertEqual(response.stats["model_calls"], 3)
        self.assertEqual(response.stats["retrieval_batch"]["status"], "candidates")

    def test_decision_and_composer_can_use_general_knowledge_after_no_match(self) -> None:
        services = FakeServices()
        services.chat_knowledge.query_status = "no_match"
        client = FakeChatClient(
            [
                {
                    "selected_region_ids": [],
                },
                chat_answer_fixture(answer="《时间简史》是一本大众科普书。"),
            ]
        )

        response = ChatAgentService(client_factory=lambda _request: client).chat(  # type: ignore[arg-type]
            _request("时间简史是什么？"), services
        )

        self.assertEqual(response.answer_provenance.mode, "general_knowledge")
        self.assertEqual(response.citations, [])
        source_event = next(event for event in response.events if event.event_type == "answer_source_selected")
        self.assertEqual(source_event.payload["source_path"], "model_general")
        self.assertFalse(source_event.payload["provisional"])
        self.assertIn("In `general` mode", client.requests[-1].messages[0].content)
        self.assertIn('"retrieval_outcome": "no_match"', client.requests[-2].messages[-1].content)
        self.assertEqual(
            [item.tool for item in response.tool_trace],
            ["retrieve_knowledge_batch"],
        )
        self.assertEqual(response.stats["model_calls"], 3)

    def test_decision_and_composer_can_preserve_local_knowledge_gap(self) -> None:
        services = FakeServices()
        services.chat_knowledge.query_status = "no_match"
        client = FakeChatClient(
            [
                {
                    "selected_region_ids": [],
                },
                chat_answer_fixture(
                    gap="缺失主题",
                    gap_markdown="当前知识库材料没有给出该主题。",
                ),
            ]
        )

        response = ChatAgentService(client_factory=lambda _request: client).chat(  # type: ignore[arg-type]
            _request("缺失主题"), services
        )

        self.assertEqual(response.answer_provenance.mode, "knowledge_gap")
        self.assertEqual(response.answer_provenance.chat_outcome, "no_match")
        self.assertEqual(response.answer, "当前知识库材料没有给出该主题。")
        self.assertEqual(response.stats["model_calls"], 3)

    def test_document_scoped_no_match_is_decided_by_answer_decision(self) -> None:
        services = FakeServices()
        services.chat_knowledge.query_status = "no_match"
        client = FakeChatClient(
            [
                {"selected_region_ids": []},
                chat_answer_fixture(
                    gap="HNSW 参数",
                    gap_markdown="当前文档没有给出 HNSW 参数。",
                ),
            ]
        )

        response = ChatAgentService(client_factory=lambda _request: client).chat(  # type: ignore[arg-type]
            _request("文档明确使用 HNSW 时给出了哪些参数？"), services
        )

        self.assertEqual(response.answer_provenance.mode, "knowledge_gap")
        self.assertEqual(response.citations, [])
        self.assertEqual(response.answer, "当前文档没有给出 HNSW 参数。")

    def test_incomplete_no_match_cannot_route_to_general_model(self) -> None:
        services = FakeServices()
        services.chat_knowledge.query_status = "no_match"
        original_search = services.chat_knowledge.search_knowledge

        def incomplete_search(context, arguments):
            observation = original_search(context, arguments)
            observation.result["query_outcomes"][0]["channel_statuses"][1]["exhausted"] = False
            return observation

        services.chat_knowledge.search_knowledge = incomplete_search  # type: ignore[method-assign]
        client = FakeChatClient(
            [
                {
                    "selected_region_ids": [],
                }
            ]
        )

        response = ChatAgentService(client_factory=lambda _request: client).chat(_request("缺失主题"), services)  # type: ignore[arg-type]

        self.assertEqual(response.answer_provenance.mode, "knowledge_gap")
        self.assertEqual(response.answer_provenance.chat_outcome, "resource_exhausted")
        self.assertEqual(response.stats["model_calls"], 1)
        self.assertNotIn("pretrained general knowledge", "\n".join(request.messages[0].content for request in client.requests))

    def test_general_output_cannot_forge_knowledge_citations(self) -> None:
        services = FakeServices()
        services.chat_knowledge.query_status = "no_match"
        client = FakeChatClient(
            [
                {
                    "selected_region_ids": [],
                },
                {
                    "mode": "general",
                    "spans": [],
                    "visuals": [],
                    "gap": None,
                    "generated_image_prompt": None,
                },
                {
                    "items": [
                        {
                            "type": "text",
                            "markdown": "回答 [1]",
                            "materials": [],
                        }
                    ],
                    "gap_markdown": None,
                },
                {
                    "items": [
                        {
                            "type": "text",
                            "markdown": "回答 [1]",
                            "materials": [],
                        }
                    ],
                    "gap_markdown": None,
                },
                {
                    "items": [
                        {
                            "type": "text",
                            "markdown": "回答 [1]",
                            "materials": [],
                        }
                    ],
                    "gap_markdown": None,
                },
            ]
        )

        with self.assertRaises(ModelOutputError):
            ChatAgentService(client_factory=lambda _request: client).chat(  # type: ignore[arg-type]
                _request("缺失主题"), services
            )

    def test_retryable_grounded_model_error_is_retried(self) -> None:
        client = FakeChatClient([_grounded()])
        client.failures_before_success = [ExternalServiceError("temporary")]
        response = ChatAgentService(client_factory=lambda _request: client).chat(_request("问题"), FakeServices())  # type: ignore[arg-type]
        self.assertEqual(response.stats["model_calls"], 3)
        self.assertGreater(len(client.requests), response.stats["model_calls"])

    def test_invalid_grounded_contract_is_retried_before_request_fails(self) -> None:
        invalid = {
            "mode": "raw",
            "spans": ["sp_missing"],
            "visuals": [],
            "gap": None,
            "generated_image_prompt": None,
        }
        client = FakeChatClient([invalid, _grounded()])

        with self.assertLogs(
            "knoarbor.services.chat_model_call",
            level="WARNING",
        ) as captured:
            response = ChatAgentService(client_factory=lambda _request: client).chat(  # type: ignore[arg-type]
                _request("Agent Loop 是什么？"), FakeServices()
            )

        self.assertEqual(response.answer_provenance.mode, "knowledge_grounded")
        self.assertEqual(len(client.requests), 4)
        self.assertIn("previous completion was rejected", client.requests[2].messages[-1].content.lower())
        self.assertIn("unknown support spans", client.requests[2].messages[-1].content)
        self.assertIn("phase=answer_decision", captured.output[0])
        self.assertIn("attempt=1", captured.output[0])
        self.assertIn("unknown support spans", captured.output[0])

    def test_answer_decision_rejects_unknown_support_span(self) -> None:
        draft = {
            "mode": "raw",
            "spans": ["sp_missing"],
            "visuals": [],
            "gap": None,
            "generated_image_prompt": None,
        }
        with self.assertRaisesRegex(ModelOutputError, "unknown support spans"):
            ChatAgentService(client_factory=lambda _request: FakeChatClient([draft, draft, draft])).chat(  # type: ignore[arg-type]
                _request("Agent Loop 是什么？"),
                FakeServices(),  # type: ignore[arg-type]
            )

    def test_composer_accepts_supported_paraphrase(self) -> None:
        draft = _grounded("智能体循环交替进行推理、行动与观察 [1]。")
        response = ChatAgentService(client_factory=lambda _request: FakeChatClient([draft])).chat(
            _request("Agent Loop 是什么？"),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(
            response.answer_provenance.mode,
            "knowledge_grounded",
        )

    def test_composer_allows_translation_without_comparable_lexical_signal(self) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:nist",
                        "raw_revision_id": "rev:nist",
                        "source_unit_id": "unit:nist",
                        "content": "Valid and reliable systems are a necessary condition of trustworthy AI.",
                    }
                ]
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_1"],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:nist"],
        )
        answer, citations = _validate_and_finalize_composition(
            ChatResponseComposerDraft.model_validate(
                {
                    "items": [
                        {
                            "type": "text",
                            "markdown": "有效且可靠是可信人工智能的必要条件。",
                            "materials": ["material_1"],
                        }
                    ],
                    "gap_markdown": None,
                }
            ),
            result,
        )

        self.assertEqual(len(citations), 1)
        self.assertIn("有效且可靠是可信人工智能的必要条件 [1]。", answer)

    def test_composer_can_synthesize_one_authorized_raw_item(self) -> None:
        draft = _grounded("材料表明 Agent Loop 存在更广泛的控制关系 [1]。")
        response = ChatAgentService(client_factory=lambda _request: FakeChatClient([draft])).chat(  # type: ignore[arg-type]
            _request("Agent Loop 有什么更广泛的关系？"),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(response.answer_provenance.mode, "knowledge_grounded")
        self.assertIn("材料表明 Agent Loop", response.answer)

    def test_grounded_synthesis_can_bind_multiple_authorized_raw_items(self) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {
                        "evidence_id": "ev:rewrite",
                        "raw_revision_id": "rawrev:rewrite",
                        "source_unit_id": "unit:rewrite",
                        "source_path": "raw/rewrite.md",
                        "content": "Query Rewrite 通过意图改写提升召回。",
                    },
                    {
                        "evidence_id": "ev:fusion",
                        "raw_revision_id": "rawrev:fusion",
                        "source_unit_id": "unit:fusion",
                        "source_path": "raw/fusion.md",
                        "content": "向量数据库通过 RRF 融合多路检索结果。",
                    },
                ]
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_1", "sp_2_1"],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:rewrite", "ev:fusion"],
        )
        answer, citations = _validate_and_finalize_composition(
            ChatResponseComposerDraft.model_validate(
                {
                    "items": [
                        {
                            "type": "text",
                            "markdown": "Query Rewrite 通过意图改写提升召回，向量数据库通过 RRF 融合多路检索结果。",
                            "materials": ["material_1", "material_2"],
                        }
                    ],
                    "gap_markdown": None,
                }
            ),
            result,
        )

        self.assertEqual(len(citations), 2)
        self.assertIn("[1] [2]", answer)

    def test_each_factual_block_keeps_its_own_adjacent_citation(self) -> None:
        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [
                    {"evidence_id": "ev:a", "raw_revision_id": "rev:a", "source_unit_id": "unit:a", "content": "机器层负责执行。"},
                    {"evidence_id": "ev:b", "raw_revision_id": "rev:b", "source_unit_id": "unit:b", "content": "应用层负责交互。"},
                ]
            },
        )
        result = _decision_result(
            [observation],
            {
                "mode": "raw",
                "spans": ["sp_1_1", "sp_2_1"],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            },
            ["ev:a", "ev:b"],
        )
        answer, _ = _validate_and_finalize_composition(
            ChatResponseComposerDraft.model_validate(
                {
                    "items": [
                        {
                            "type": "text",
                            "markdown": "- 机器层负责执行。",
                            "materials": ["material_1"],
                        },
                        {
                            "type": "text",
                            "markdown": "- 应用层负责交互。",
                            "materials": ["material_2"],
                        },
                    ],
                    "gap_markdown": None,
                }
            ),
            result,
        )

        self.assertIn("- 机器层负责执行 [1]。", answer)
        self.assertIn("- 应用层负责交互 [2]。", answer)

    def test_cancellation_after_model_return_prevents_session_commit(self) -> None:
        cancellation = OperationCancellationToken()

        class CancellingClient(FakeChatClient):
            def complete(self, request):
                completion = super().complete(request)
                cancellation.stop()
                return completion

        client = CancellingClient([_grounded()])
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            with self.assertRaises(RunCancelled):
                ChatAgentService(client_factory=lambda _request: client).chat(
                    _request("问题").model_copy(update={"vault_path": tmp}),
                    services,  # type: ignore[arg-type]
                    cancellation=cancellation,
                )
            sessions = services.chat_sessions.list_sessions(tmp)
        self.assertEqual(sessions.sessions, [])

    def test_greeting_is_direct_capability_without_retrieval_or_model(self) -> None:
        response = ChatAgentService(client_factory=lambda _request: FakeChatClient([])).chat(_request("你好"), FakeServices())  # type: ignore[arg-type]
        self.assertEqual(response.answer_provenance.mode, "direct_capability")
        self.assertEqual(response.tool_trace, [])

    def test_source_image_request_forbidding_generation_never_enters_direct_image_capability(self) -> None:
        question = "展示 NASA Systems Engineering Engine 的文档原图，并解释系统设计、" "产品实现和技术管理三组流程。不要生成新图。"

        self.assertIsNone(_direct_capability(question))

    def test_compound_image_and_explanation_request_stays_on_chat_mainline(self) -> None:
        question = "生成一张 NASA 风险三元组示意图，并解释触发缓解与应急计划的条件。"

        self.assertIsNone(_direct_capability(question))

    def test_navigator_selects_multiple_regions_in_one_batch(self) -> None:
        catalog = {
            "schema_version": "active_corpus_outline.v1",
            "authority": "query_locator_only",
            "vaults": [
                {
                    "vault_id": "test",
                    "vault_name": "Test",
                    "documents": [
                        {"region_id": "region_a", "title": "A", "source_name": "a.pdf", "source_type": "pdf", "sections": []},
                        {"region_id": "region_b", "title": "B", "source_name": "b.pdf", "source_type": "pdf", "sections": []},
                    ],
                }
            ],
            "document_count": 2,
            "region_count": 2,
        }
        client = FakeChatClient(
            [
                {
                    "searches": [
                        {
                            "region_id": "region_a",
                            "search_query": "Compare source A.",
                        },
                        {
                            "region_id": "region_b",
                            "search_query": "Compare source B.",
                        },
                    ],
                },
                chat_answer_fixture(
                    answer="Agent Loop 是推理、行动和观察的循环。",
                    spans=["sp_1_1"],
                ),
            ]
        )
        services = FakeServices()
        with patch(
            "knoarbor.services.chat_agent.build_active_corpus_catalog",
            return_value=catalog,
        ):
            response = ChatAgentService(client_factory=lambda _request: client).chat(
                _request("比较 A 和 B 的区别"),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(response.stats["model_calls"], 3)
        self.assertEqual(
            [item.tool for item in response.tool_trace],
            ["retrieve_knowledge_batch"],
        )
        self.assertEqual(
            [item["query"] for item in response.stats["retrieval_batch"]["query_expressions"]],
            [
                "比较 A 和 B 的区别",
                "Compare source A.",
                "比较 A 和 B 的区别",
                "Compare source B.",
            ],
        )
        self.assertEqual(
            [item["region_id"] for item in response.stats["retrieval_batch"]["query_expressions"]],
            ["region_a", "region_a", "region_b", "region_b"],
        )
        self.assertEqual(
            [item["group_id"] for item in response.stats["retrieval_batch"]["query_expressions"]],
            [
                "region:region_a",
                "region:region_a",
                "region:region_b",
                "region:region_b",
            ],
        )
        self.assertNotIn("coverage_objective", response.tool_trace[0].arguments)
        self.assertEqual(response.stats["retrieval_attempts"], 1)
        self.assertEqual(response.stats["retrieval_batch"]["status"], "candidates")

    def test_retrieval_planner_accepts_expression_in_a_different_script(
        self,
    ) -> None:
        catalog = {
            "schema_version": "active_corpus_outline.v1",
            "authority": "query_locator_only",
            "vaults": [
                {
                    "vault_id": "test",
                    "vault_name": "Test",
                    "documents": [
                        {
                            "region_id": "region_nasa",
                            "title": "NASA Systems Engineering",
                            "source_name": "nasa.pdf",
                            "source_type": "pdf",
                            "language_hint": "en",
                            "sections": [],
                        }
                    ],
                }
            ],
            "document_count": 1,
            "region_count": 1,
        }
        client = FakeChatClient(
            [
                {
                    "searches": [
                        {
                            "region_id": "region_nasa",
                            "search_query": "风险三元组由哪三个部分构成",
                        }
                    ],
                },
                _grounded(),
            ]
        )
        with patch(
            "knoarbor.services.chat_agent.build_active_corpus_catalog",
            return_value=catalog,
        ):
            response = ChatAgentService(client_factory=lambda _request: client).chat(
                _request("这里的风险具体由哪三个部分构成？"),
                FakeServices(),  # type: ignore[arg-type]
            )

        self.assertEqual(len(client.requests), 3)
        self.assertEqual(
            [item["query"] for item in response.stats["retrieval_batch"]["query_expressions"]],
            [
                "这里的风险具体由哪三个部分构成？",
                "风险三元组由哪三个部分构成",
            ],
        )

    def test_navigation_compiles_selected_regions_to_literal_query_directions(
        self,
    ) -> None:
        directions = _retrieval_search_directions(
            query="NIST AI RMF 与人工智能安全治理框架如何贯穿风险治理？",
            plan=ChatRetrievalPlan(
                searches=[
                    ChatRegionSearch(
                        region_id="region_nist",
                        search_query="How does the NIST AI RMF govern AI risk?",
                    ),
                    ChatRegionSearch(
                        region_id="region_cac",
                        search_query="人工智能安全治理框架如何贯穿风险治理？",
                    ),
                ]
            ),
        )

        self.assertEqual(
            directions,
            [
                (
                    "NIST AI RMF 与人工智能安全治理框架如何贯穿风险治理？",
                    "region_nist",
                    "region:region_nist",
                ),
                (
                    "How does the NIST AI RMF govern AI risk?",
                    "region_nist",
                    "region:region_nist",
                ),
                (
                    "NIST AI RMF 与人工智能安全治理框架如何贯穿风险治理？",
                    "region_cac",
                    "region:region_cac",
                ),
                (
                    "人工智能安全治理框架如何贯穿风险治理？",
                    "region_cac",
                    "region:region_cac",
                ),
            ],
        )

    def test_empty_navigation_uses_literal_only_plan(
        self,
    ) -> None:
        client = FakeChatClient(
            [
                {
                    "selected_region_ids": [],
                },
                _grounded(),
            ]
        )

        response = ChatAgentService(client_factory=lambda _request: client).chat(
            _request("比较 Alpha 和 Beta"),
            FakeServices(),  # type: ignore[arg-type]
        )

        self.assertEqual(
            [item["query"] for item in response.stats["retrieval_batch"]["query_expressions"]],
            ["比较 Alpha 和 Beta"],
        )
        self.assertEqual(len(client.requests), 3)

    def test_contextual_navigation_receives_dialogue_without_replaying_evidence(
        self,
    ) -> None:
        client = FakeChatClient(
            [
                {
                    "selected_region_ids": [],
                },
                _grounded(),
                {
                    "selected_region_ids": [],
                },
                _grounded(),
            ]
        )
        services = FakeServices()
        with tempfile.TemporaryDirectory() as tmp:
            first = ChatAgentService(client_factory=lambda _request: client).chat(
                _request("解释 Agent Loop").model_copy(update={"vault_path": tmp}),
                services,  # type: ignore[arg-type]
            )
            second_request = _request("把刚才内容改成表格").model_copy(
                update={
                    "vault_path": tmp,
                    "session_id": first.session_id,
                    "expected_session_revision": first.session_revision,
                }
            )
            second = ChatAgentService(client_factory=lambda _request: client).chat(
                second_request,
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(
            [item["query"] for item in second.stats["retrieval_batch"]["query_expressions"]],
            [
                "把刚才内容改成表格",
            ],
        )
        planning_request = next(
            request
            for request in client.requests
            if '"latest_user_message": "把刚才内容改成表格"' in request.messages[-1].content
            and '"planning_state"' in request.messages[-1].content
        )
        planning_state = __import__("json").loads(planning_request.messages[-1].content)["planning_state"]
        self.assertTrue(planning_state["conversation_context"])
        self.assertNotIn("raw_evidence", planning_request.messages[-1].content)

    def test_grounded_support_cannot_use_unauthorized_evidence(self) -> None:
        observation = FakeServices().chat_knowledge.retrieve_knowledge_batch(  # type: ignore[arg-type]
            None,
            {"query_expressions": [{"query_id": "q1", "query": "Agent Loop"}]},
        )
        decision = ChatAnswerDecision.model_validate(
            {
                "mode": "raw",
                "spans": ["sp_1_1"],
                "visuals": [],
                "gap": None,
                "generated_image_prompt": None,
            }
        )

        with self.assertRaisesRegex(ModelOutputError, "outside current Query evidence"):
            _validate_and_project_decision(
                decision,
                _prepared_evidence([observation]),
                evidence_ids=[],
                image_generation_available=False,
            )

    def test_agent_rejects_removed_dimension_output_after_retrieval(self) -> None:
        invalid = {
            "dimension_coverage": [
                {
                    "dimension_id": dimension_id,
                    "coverage_kind": "direct",
                    "materials": [{"spans": ["sp_1_1"], "visuals": []}],
                }
                for dimension_id in ("d1", "d2")
            ],
        }
        client = FakeChatClient([invalid, invalid, invalid])

        with self.assertRaisesRegex(ModelOutputError, "violated its output contract"):
            ChatAgentService(client_factory=lambda _request: client).chat(  # type: ignore[arg-type]
                _request("比较 A 和 B 的区别"),
                FakeServices(),
            )


if __name__ == "__main__":
    unittest.main()
