from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knoarbor.core.errors import ModelOutputError, UserInputError
from knoarbor.core.schemas.chat import (
    ChatAnswerProvenance,
    ChatCitation,
    ChatMessageItem,
    ChatRequest,
    ChatResponse,
    ChatSessionRetryRequest,
    ChatToolTraceItem,
)
from knoarbor.core.schemas.image_generation import GeneratedImage
from knoarbor.services.chat_agent import ChatAgentService
from knoarbor.services.chat_context import _model_visible_assistant_text
from knoarbor.services.chat_session_workflow import retry_chat_session_turn
from knoarbor.services.chat_sessions import ChatSessionStore
from knoarbor.services.chat_generated_images import store_chat_generated_image
from knoarbor.storage.vault_layout import chat_session_artifacts_root
from tests.helpers.chat_fakes import FakeChatClient, FakeServices, chat_answer_fixture


PROVENANCE = ChatAnswerProvenance(
    mode="knowledge_grounded",
    query_outcome="candidates",
    chat_outcome="sufficient",
)


def _grounded(answer: str) -> dict[str, object]:
    return chat_answer_fixture(
        answer=answer.replace(" [1]", ""),
        spans=["sp_1_1"],
    )


def _request(content: str, vault: str, *, session_id: str | None = None) -> ChatRequest:
    return ChatRequest(
        session_id=session_id,
        expected_session_revision=1 if session_id is not None else None,
        message=ChatMessageItem(role="user", content=content),
        vault_path=vault,
        append_ledger=False,
    )


class ChatSessionTest(unittest.TestCase):
    def test_v3_session_is_migrated_without_losing_dialogue_or_provenance(self) -> None:
        store = ChatSessionStore()
        response = ChatResponse(
            request_id="req_migrate",
            execution_id="exec_migrate",
            session_id="chat_migrate",
            session_revision=1,
            turn_id="turn_migrate",
            answer="迁移后的回答 [1]。",
            answer_provenance=PROVENANCE,
            citations=[ChatCitation(
                kind="raw_evidence",
                evidence_id="ev:migrate",
                raw_revision_id="rawrev:migrate",
                source_unit_id="unit:migrate",
            )],
            stats={"model_calls": 1},
        )
        with tempfile.TemporaryDirectory() as tmp:
            store.persist_response(
                tmp,
                response=response,
                request_messages=[ChatMessageItem(role="user", content="迁移问题")],
                vault_id="test",
                vault_name="Test",
            )
            path = next((Path(tmp) / ".knoarbor" / "chat" / "sessions").glob("chat_*.json"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["schema_version"] = "chat_session.v3"
            payload["topic_anchor"] = {"canonical_query": "legacy"}
            payload["retrieval_continuation"] = {"reason": "legacy"}
            payload["stats"]["turn_intent"] = {"question_dimensions": []}
            payload["turns"][0]["topic_anchor"] = {"canonical_query": "legacy"}
            payload["turns"][0]["retrieval_continuation"] = {"reason": "legacy"}
            payload["turns"][0]["tool_trace"] = [{
                "tool": "retrieve_knowledge_batch",
                "result": {
                    "raw_evidence": [{
                        "evidence_id": "ev:migrate",
                        "source_unit_id": "unit:migrate",
                        "content": "LEGACY DUPLICATED RAW",
                        "excerpt": "LEGACY DUPLICATED RAW",
                    }]
                },
            }]
            payload["tool_trace"] = payload["turns"][0]["tool_trace"]
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            migrated = store.read_session(tmp, "chat_migrate")

        self.assertEqual(migrated.schema_version, "chat_session.v4")
        self.assertEqual([message.content for message in migrated.messages], [
            "迁移问题",
            "迁移后的回答 [1]。",
        ])
        self.assertEqual(migrated.turns[0].citations[0].evidence_id, "ev:migrate")
        self.assertEqual(migrated.turns[0].answer_provenance, PROVENANCE)
        self.assertNotIn("turn_intent", migrated.stats)
        self.assertEqual(migrated.tool_trace, [])
        migrated_evidence = (
            migrated.turns[0].tool_trace[0].result["raw_evidence"][0]
        )
        self.assertEqual(migrated_evidence["excerpt"], "")
        self.assertNotIn("content", migrated_evidence)

    def test_session_list_reads_summary_without_materializing_turn_trace(
        self,
    ) -> None:
        store = ChatSessionStore()
        response = ChatResponse(
            request_id="req_summary",
            execution_id="exec_summary",
            session_id="chat_summary",
            session_revision=1,
            turn_id="turn_summary",
            answer="Summary answer.",
            answer_provenance=PROVENANCE,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store.persist_response(
                tmp,
                response=response,
                request_messages=[
                    ChatMessageItem(role="user", content="Summary question")
                ],
                vault_id="test",
                vault_name="Test",
            )
            with patch.object(
                store,
                "_read_record_path",
                side_effect=AssertionError("full session must not be read"),
            ):
                listed = store.list_sessions(tmp)

        self.assertEqual(len(listed.sessions), 1)
        self.assertEqual(listed.sessions[0].session_id, "chat_summary")
        self.assertEqual(listed.sessions[0].message_count, 2)
        self.assertEqual(listed.sessions[0].last_message, "Summary answer.")
        self.assertEqual(listed.total_count, 1)
        self.assertFalse(listed.has_more)

    def test_session_list_paginates_without_hiding_older_summaries(self) -> None:
        store = ChatSessionStore()
        with tempfile.TemporaryDirectory() as tmp:
            for ordinal in range(5):
                store.persist_response(
                    tmp,
                    response=ChatResponse(
                        request_id=f"req_{ordinal}",
                        execution_id=f"exec_{ordinal}",
                        session_id=f"chat_page_{ordinal}",
                        session_revision=1,
                        turn_id=f"turn_{ordinal}",
                        answer=f"Answer {ordinal}",
                        answer_provenance=PROVENANCE,
                    ),
                    request_messages=[
                        ChatMessageItem(
                            role="user",
                            content=f"Question {ordinal}",
                        )
                    ],
                    vault_id="test",
                    vault_name="Test",
                )

            first = store.list_sessions(tmp, limit=2)
            second = store.list_sessions(tmp, limit=2, offset=2)
            third = store.list_sessions(tmp, limit=2, offset=4)

        self.assertEqual(first.total_count, 5)
        self.assertEqual(first.offset, 0)
        self.assertTrue(first.has_more)
        self.assertEqual(second.offset, 2)
        self.assertTrue(second.has_more)
        self.assertEqual(third.offset, 4)
        self.assertFalse(third.has_more)
        self.assertEqual(
            {
                session.session_id
                for page in (first, second, third)
                for session in page.sessions
            },
            {f"chat_page_{ordinal}" for ordinal in range(5)},
        )

    def test_session_persists_evidence_handles_without_raw_content_or_duplicate_trace(self) -> None:
        store = ChatSessionStore()
        raw_content = "full raw evidence must remain authoritative in the vault" * 100
        trace = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            arguments={"evidence_ids": ["ev:test"]},
            citations=[
                ChatCitation(
                    kind="raw_evidence",
                    evidence_id="ev:test",
                    raw_revision_id="rawrev:test",
                    source_unit_id="unit:test",
                )
            ],
            result={
                "raw_evidence": [{
                    "evidence_id": "ev:test",
                    "raw_record_id": "raw:test",
                    "raw_revision_id": "rawrev:test",
                    "source_unit_id": "unit:test",
                    "source_record_id": "source:test",
                    "processing_record_id": "processing:test",
                    "source_path": "raw/test.md",
                    "title": "Test evidence",
                    "excerpt": raw_content,
                    "content": raw_content,
                    "locator_page_paths": ["wiki/pages/test.md"],
                    "attachments": [{"content": raw_content}],
                }],
                "factual_authority": "active_raw_source_unit",
            },
        )
        response = ChatResponse(
            request_id="req_compact",
            execution_id="exec_compact",
            session_id="chat_compact",
            session_revision=1,
            turn_id="turn_compact",
            answer="Grounded answer.",
            answer_provenance=PROVENANCE,
            tool_trace=[trace],
        )

        with tempfile.TemporaryDirectory() as tmp:
            persisted = store.persist_response(
                tmp,
                response=response,
                request_messages=[ChatMessageItem(role="user", content="Question")],
                vault_id="test",
                vault_name="Test",
            )
            session_text = next((Path(tmp) / ".knoarbor" / "chat" / "sessions").glob("chat_*.json")).read_text()

        self.assertEqual(persisted.tool_trace, [])
        handle = persisted.turns[0].tool_trace[0].result["raw_evidence"][0]
        self.assertEqual(handle["evidence_id"], "ev:test")
        self.assertEqual(handle["locator_page_paths"], ["wiki/pages/test.md"])
        self.assertEqual(handle["excerpt"], "")
        self.assertNotIn("content", handle)
        self.assertNotIn("attachments", handle)
        self.assertNotIn(raw_content, session_text)
        self.assertEqual(response.tool_trace[0].result["raw_evidence"][0]["content"], raw_content)

    def test_session_and_turn_deletion_remove_owned_generated_images(self) -> None:
        store = ChatSessionStore()
        with tempfile.TemporaryDirectory() as tmp:
            session_id = "chat_images"
            first_image = store_chat_generated_image(
                GeneratedImage(b64_json="Zmlyc3Q=", mime_type="image/png"),
                vault_path=tmp,
                session_id=session_id,
                request_id="req_first",
                index=1,
            )
            assert first_image is not None
            first = ChatResponse(
                request_id="req_first",
                execution_id="exec_first",
                session_id=session_id,
                session_revision=1,
                turn_id="turn_first",
                answer="![Generated image](local)",
                answer_provenance=ChatAnswerProvenance(mode="direct_capability", query_outcome="not_applicable", chat_outcome="direct"),
                tool_trace=[ChatToolTraceItem(tool="generate_image", result={"images": [{"stored_path": first_image.path}]})],
            )
            store.persist_response(tmp, response=first, request_messages=[ChatMessageItem(role="user", content="画图")], vault_id="test", vault_name="Test")

            removed = store.remove_turn(tmp, session_id, first.turn_id, first.session_revision)
            self.assertFalse(Path(first_image.path).exists())
            self.assertFalse(chat_session_artifacts_root(Path(tmp), session_id).exists())

            second_image = store_chat_generated_image(
                GeneratedImage(b64_json="c2Vjb25k", mime_type="image/png"),
                vault_path=tmp,
                session_id=session_id,
                request_id="req_second",
                index=1,
            )
            assert second_image is not None
            second = ChatResponse(
                request_id="req_second",
                execution_id="exec_second",
                session_id=session_id,
                session_revision=removed.session_revision + 1,
                turn_id="turn_second",
                answer="![Generated image](local)",
                answer_provenance=first.answer_provenance,
                tool_trace=[ChatToolTraceItem(tool="generate_image", result={"images": [{"stored_path": second_image.path}]})],
            )
            persisted = store.persist_response(tmp, response=second, request_messages=[ChatMessageItem(role="user", content="再画图")], vault_id="test", vault_name="Test")
            store.delete_session(tmp, session_id, persisted.session_revision)
            self.assertFalse(chat_session_artifacts_root(Path(tmp), session_id).exists())

    def test_v3_retry_contract_rejects_removed_policy(self) -> None:
        with self.assertRaises(Exception):
            ChatSessionRetryRequest.model_validate(
                {
                    "schema_version": "chat_session_retry_request.v3",
                    "target_turn_id": "turn:test",
                    "expected_session_revision": 1,
                    "answer_policy": "knowledge_only",
                }
            )

    def test_resource_retry_starts_a_fresh_batch_without_chat_continuation(self) -> None:
        class ResumableKnowledge:
            def __init__(self) -> None:
                self.batch_arguments: list[dict[str, object]] = []

            def retrieve_knowledge_batch(self, _context, arguments):
                self.batch_arguments.append(arguments)
                resumed = len(self.batch_arguments) == 2
                evidence_id = "ev:after-boundary" if resumed else "ev:before-boundary"
                evidence = (
                    {
                        "evidence_id": evidence_id,
                        "raw_record_id": "raw:0",
                        "raw_revision_id": "rawrev:test",
                        "source_unit_id": "unit:0",
                        "source_record_id": "source:0",
                        "processing_record_id": "processing:0",
                        "source_path": "raw/0.md",
                        "unit_index": 0,
                        "unit_type": "section",
                        "title": "Evidence 0",
                        "excerpt": "Evidence content 0",
                        "content": "Evidence content 0",
                        "excerpt_hash": "sha256:0",
                    }
                    if resumed
                    else None
                )
                citations = (
                    ChatCitation(
                        kind="raw_evidence",
                        role="source",
                        path="raw/0.md",
                        evidence_id=evidence_id,
                        raw_revision_id="rawrev:test",
                        source_unit_id="unit:0",
                    )
                    if resumed
                    else None
                )
                return ChatToolTraceItem(
                    tool="retrieve_knowledge_batch",
                    arguments=arguments,
                    citations=[citations] if citations else [],
                    result={
                        "status": "candidates" if resumed else "resource_exhausted",
                        "query_expressions": arguments["query_expressions"],
                        "query_results": [],
                        "raw_evidence": [evidence] if evidence else [],
                        "selected_evidence_ids": [evidence_id] if resumed else [],
                        "evidence_query_ids": {evidence_id: ["q1"]} if resumed else {},
                        "candidate_count": 1 if resumed else 0,
                        "raw_read_rounds": 1 if resumed else 0,
                        "raw_read_count": 1 if resumed else 0,
                        "warnings": [],
                    },
                )

        client = FakeChatClient([
            chat_answer_fixture(
                answer="Evidence content。",
                spans=["sp_1_1"],
            ),
        ])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            knowledge = ResumableKnowledge()
            services.chat_knowledge = knowledge  # type: ignore[assignment]
            services.chat = service  # type: ignore[attr-defined]
            first = service.chat(_request("跨边界问题", tmp), services)  # type: ignore[arg-type]
            retried = retry_chat_session_turn(
                services,  # type: ignore[arg-type]
                first.session_id,
                ChatSessionRetryRequest(
                    vault_path=tmp,
                    target_turn_id=first.turn_id,
                    expected_session_revision=first.session_revision,
                    append_ledger=False,
                ),
            )

        self.assertNotIn("continuation_cursors", knowledge.batch_arguments[0])
        self.assertNotIn("continuation_cursors", knowledge.batch_arguments[1])
        self.assertEqual(retried.answer_provenance.mode, "knowledge_grounded")

    def test_v4_session_persists_provenance_and_continues(self) -> None:
        client = FakeChatClient([
            _grounded("第一轮回答：Agent Loop 是推理、行动和观察的循环 [1]。"),
            _grounded("第二轮回答：Agent Loop 是推理、行动和观察的循环 [1]。"),
        ])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(_request("第一轮问题", tmp), services)  # type: ignore[arg-type]
            second = service.chat(_request("第二轮问题", tmp, session_id=first.session_id), services)  # type: ignore[arg-type]
            record = services.chat_sessions.read_session(tmp, second.session_id)

        self.assertEqual(record.schema_version, "chat_session.v4")
        self.assertEqual(record.session_revision, 2)
        self.assertEqual(len(record.turns), 2)
        self.assertEqual(record.turns[0].answer_provenance.mode, "knowledge_grounded")
        self.assertEqual(
            [message.content for message in record.messages],
            [
                "第一轮问题",
                "第一轮回答：Agent Loop 是推理、行动和观察的循环 [1]。",
                "第二轮问题",
                "第二轮回答：Agent Loop 是推理、行动和观察的循环 [1]。",
            ],
        )
        answer_state = __import__("json").loads(client.requests[-1].messages[-1].content)["composition_state"]
        self.assertEqual(
            answer_state["conversation_context"],
            [{
                "user": "第一轮问题",
                "assistant": "第一轮回答：Agent Loop 是推理、行动和观察的循环。",
            }],
        )
        self.assertNotIn("citation_paths", answer_state["conversation_context"][0])
        self.assertNotIn("tool_trace", answer_state["conversation_context"][0])

    def test_complete_dialogue_history_has_no_turn_or_answer_truncation(self) -> None:
        long_answer = "完整回答" * 400
        client = FakeChatClient([_grounded(long_answer) for _ in range(8)])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            session_id = None
            revision = None
            for index in range(8):
                response = service.chat(
                    ChatRequest(
                        session_id=session_id,
                        expected_session_revision=revision,
                        message=ChatMessageItem(role="user", content=f"第{index + 1}轮问题"),
                        vault_path=tmp,
                        append_ledger=False,
                    ),
                    services,  # type: ignore[arg-type]
                )
                session_id = response.session_id
                revision = response.session_revision

        answer_state = __import__("json").loads(client.requests[-1].messages[-1].content)["composition_state"]
        dialogue = answer_state["conversation_context"]
        self.assertEqual(len(dialogue), 7)
        self.assertEqual(dialogue[0]["user"], "第1轮问题")
        self.assertEqual(dialogue[-1]["user"], "第7轮问题")
        self.assertGreater(len(dialogue[0]["assistant"]), 1200)
        self.assertEqual(set(dialogue[0]), {"user", "assistant"})

    def test_retrieval_planner_receives_dialogue_without_prior_retrieval_metadata(self) -> None:
        client = FakeChatClient([
            _grounded("第一轮有依据的回答 [1]。"),
            {
                "selected_region_ids": [],
            },
            chat_answer_fixture(answer="第二轮通用回答。"),
        ])
        service = ChatAgentService(
            client_factory=lambda _request: client,
        )
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(_request("第一轮问题", tmp), services)  # type: ignore[arg-type]
            services.chat_knowledge.query_status = "no_match"
            service.chat(
                _request("第二轮普通问题", tmp, session_id=first.session_id),
                services,  # type: ignore[arg-type]
            )

        navigator_request = [
            request
            for request in client.requests
            if "retrieval planner" in request.messages[0].content.lower()
        ][-1]
        planning_state = __import__("json").loads(
            navigator_request.messages[-1].content
        )["planning_state"]
        self.assertEqual(
            planning_state["conversation_context"],
            [{"user": "第一轮问题", "assistant": "第一轮有依据的回答。"}],
        )
        for forbidden in (
            "prior_evidence_context",
            "recent_turns",
            "citation_paths",
            "tool_summaries",
        ):
            self.assertNotIn(forbidden, planning_state)

    def test_model_dialogue_removes_rendered_citations_and_images_only(self) -> None:
        content = (
            "公式中的 [1] 不应删除，正文保留 [1]。\n\n"
            "![源图](/vault-assets/source.png)\n\n"
            "**本轮生成图片（非知识库证据）**\n\n"
            "![Generated image 1](/chat-assets/generated.png)\n\n"
            "用户要求保留的 [9]。"
        )

        cleaned = _model_visible_assistant_text(content, citation_count=1)

        self.assertEqual(
            cleaned,
            "公式中的 [1] 不应删除，正文保留。\n\n用户要求保留的 [9]。",
        )

    def test_follow_up_retries_unknown_navigation_region_and_uses_catalog_region(
        self,
    ) -> None:
        catalog = {
            "schema_version": "active_corpus_outline.v1",
            "authority": "query_locator_only",
            "vaults": [{
                "vault_id": "test",
                "vault_name": "Test",
                "documents": [{
                    "region_id": "region_nist",
                    "title": "NIST AI RMF",
                    "source_name": "nist.pdf",
                    "source_type": "pdf",
                    "sections": [{
                        "region_id": "region_govern",
                        "title": "GOVERN",
                    }],
                }],
            }],
            "document_count": 1,
            "region_count": 2,
        }
        client = FakeChatClient([
            _grounded("NIST AI RMF 包含 GOVERN、MAP、MEASURE、MANAGE [1]。"),
            {
                "selected_region_ids": ["invented-region"],
            },
            {
                "selected_region_ids": ["region_govern"],
            },
            _grounded("GOVERN 负责建立组织治理结构 [1]。"),
        ])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            with patch(
                "knoarbor.services.chat_agent.build_active_corpus_catalog",
                return_value=catalog,
            ):
                first = service.chat(
                    _request("NIST AI RMF Core 有哪些函数？", tmp),
                    services,  # type: ignore[arg-type]
                )
                second = service.chat(
                    _request(
                        "其中哪个函数负责建立组织治理结构？",
                        tmp,
                        session_id=first.session_id,
                    ),
                    services,  # type: ignore[arg-type]
                )

        self.assertEqual(
            [
                item["query"]
                for item in second.stats["retrieval_batch"][
                    "query_expressions"
                ]
            ],
            ["其中哪个函数负责建立组织治理结构？"],
        )
        self.assertEqual(
            second.stats["retrieval_batch"]["query_expressions"][0]["region_id"],
            "region_govern",
        )
        navigator_requests = [
            request
            for request in client.requests
            if "retrieval planner" in request.messages[0].content.lower()
        ]
        self.assertEqual(len(navigator_requests), 3)

    def test_prepare_retry_does_not_remove_previous_turn(self) -> None:
        client = FakeChatClient([_grounded("第一版：Agent Loop 是推理、行动和观察的循环 [1]。")])
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            response = ChatAgentService(client_factory=lambda _request: client).chat(_request("问题", tmp), services)  # type: ignore[arg-type]
            previous, user = services.chat_sessions.prepare_retry_turn(
                tmp,
                response.session_id,
                response.turn_id,
                response.session_revision,
            )
            current = services.chat_sessions.read_session(tmp, response.session_id)

        self.assertEqual(user.content, "问题")
        self.assertEqual(current.turns, previous.turns)
        self.assertEqual(current.messages, previous.messages)

    def test_retry_replaces_latest_turn_in_one_session_revision(self) -> None:
        client = FakeChatClient([
            _grounded("第一版：Agent Loop 是推理、行动和观察的循环 [1]。"),
            _grounded("第二版：Agent Loop 是推理、行动和观察的循环 [1]。"),
        ])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            services.chat = service  # type: ignore[attr-defined]
            first = service.chat(_request("问题", tmp), services)  # type: ignore[arg-type]
            retried = retry_chat_session_turn(
                services,  # type: ignore[arg-type]
                first.session_id,
                ChatSessionRetryRequest(
                    vault_path=tmp,
                    target_turn_id=first.turn_id,
                    expected_session_revision=first.session_revision,
                    append_ledger=False,
                ),
            )
            record = services.chat_sessions.read_session(tmp, first.session_id)

        self.assertEqual(record.session_revision, 2)
        self.assertEqual(len(record.turns), 1)
        self.assertEqual(record.turns[0].turn_id, retried.turn_id)
        self.assertNotEqual(record.turns[0].turn_id, first.turn_id)
        self.assertEqual(
            [message.content for message in record.messages],
            ["问题", "第二版：Agent Loop 是推理、行动和观察的循环 [1]。"],
        )
        answer_state = __import__("json").loads(client.requests[-1].messages[-1].content)["composition_state"]
        self.assertEqual(answer_state["conversation_context"], [])

    def test_failed_retry_leaves_previous_turn_unchanged(self) -> None:
        first_service = ChatAgentService(
            client_factory=lambda _request: FakeChatClient(
                [_grounded("第一版：Agent Loop 是推理、行动和观察的循环 [1]。")]
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = first_service.chat(_request("问题", tmp), services)  # type: ignore[arg-type]
            before = services.chat_sessions.read_session(tmp, first.session_id)
            invalid = {"answer_markdown": "无覆盖声明"}
            services.chat = ChatAgentService(client_factory=lambda _request: FakeChatClient([invalid, invalid, invalid]))  # type: ignore[attr-defined]
            with self.assertRaises(ModelOutputError):
                retry_chat_session_turn(
                    services,  # type: ignore[arg-type]
                    first.session_id,
                    ChatSessionRetryRequest(
                        vault_path=tmp,
                        target_turn_id=first.turn_id,
                        expected_session_revision=first.session_revision,
                        append_ledger=False,
                    ),
                )
            after = services.chat_sessions.read_session(tmp, first.session_id)

        self.assertEqual(after, before)

    def test_duplicate_request_identity_does_not_append_or_replace_turn(self) -> None:
        client = FakeChatClient([
            _grounded("第一版：Agent Loop 是推理、行动和观察的循环 [1]。"),
            _grounded("不应持久化的第二版：Agent Loop 是推理、行动和观察的循环 [1]。"),
        ])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            request = _request("问题", tmp)
            first = service.chat(request, services)  # type: ignore[arg-type]
            duplicate_request = request.model_copy(update={"session_id": first.session_id, "expected_session_revision": 1})
            duplicate = service.chat(duplicate_request, services)  # type: ignore[arg-type]
            record = services.chat_sessions.read_session(tmp, first.session_id)

        self.assertEqual(len(record.turns), 1)
        self.assertEqual(record.session_revision, 1)
        self.assertEqual(duplicate.answer, first.answer)
        self.assertEqual(duplicate.turn_id, first.turn_id)

    def test_stale_session_revision_is_rejected_before_execution(self) -> None:
        client = FakeChatClient([_grounded("第一轮：Agent Loop 是推理、行动和观察的循环 [1]。")])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(_request("第一轮", tmp), services)  # type: ignore[arg-type]
            stale = _request("第二轮", tmp, session_id=first.session_id).model_copy(update={"expected_session_revision": 99})
            with self.assertRaisesRegex(Exception, "revision changed"):
                service.chat(stale, services)  # type: ignore[arg-type]

    def test_turn_delete_uses_stable_identity_and_compare_and_swap(self) -> None:
        client = FakeChatClient([
            _grounded("第一轮：Agent Loop 是推理、行动和观察的循环 [1]。"),
            _grounded("第二轮：Agent Loop 是推理、行动和观察的循环 [1]。"),
        ])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(_request("第一问", tmp), services)  # type: ignore[arg-type]
            second = service.chat(_request("第二问", tmp, session_id=first.session_id), services)  # type: ignore[arg-type]
            updated = services.chat_sessions.remove_turn(
                tmp,
                second.session_id,
                first.turn_id,
                second.session_revision,
            )
            with self.assertRaisesRegex(Exception, "revision changed"):
                services.chat_sessions.remove_turn(
                    tmp,
                    second.session_id,
                    second.turn_id,
                    second.session_revision,
                )

        self.assertEqual(updated.session_revision, 3)
        self.assertEqual([turn.turn_id for turn in updated.turns], [second.turn_id])
        self.assertEqual(updated.turns[0].index, 0)
        self.assertEqual(
            [message.content for message in updated.messages],
            ["第二问", "第二轮：Agent Loop 是推理、行动和观察的循环 [1]。"],
        )

    def test_selected_chat_ingest_resolves_stable_turn_ids_at_revision(self) -> None:
        client = FakeChatClient([
            _grounded("第一轮：Agent Loop 是推理、行动和观察的循环 [1]。"),
            _grounded("第二轮：Agent Loop 是推理、行动和观察的循环 [1]。"),
        ])
        service = ChatAgentService(client_factory=lambda _request: client)
        with tempfile.TemporaryDirectory() as tmp:
            services = FakeServices()
            first = service.chat(_request("第一问", tmp), services)  # type: ignore[arg-type]
            second = service.chat(_request("第二问", tmp, session_id=first.session_id), services)  # type: ignore[arg-type]
            document = services.chat_sessions.to_source_document(
                tmp,
                second.session_id,
                turn_ids=[second.turn_id],
                expected_session_revision=second.session_revision,
            )
            with self.assertRaisesRegex(Exception, "revision changed"):
                services.chat_sessions.to_source_document(
                    tmp,
                    second.session_id,
                    turn_ids=[second.turn_id],
                    expected_session_revision=first.session_revision,
                )

        payload = __import__("json").loads(document.content.text)
        self.assertEqual(
            [message["content"] for message in payload["messages"]],
            ["第二问", "第二轮：Agent Loop 是推理、行动和观察的循环 [1]。"],
        )

    def test_general_turn_cannot_be_promoted_to_chat_ingest(self) -> None:
        store = ChatSessionStore()
        with tempfile.TemporaryDirectory() as tmp:
            response = ChatResponse(
                request_id="req_general",
                execution_id="exec_general",
                session_id="chat_general1234",
                session_revision=1,
                turn_id="turn_general",
                answer="通用知识回答。",
                answer_provenance=ChatAnswerProvenance(
                    mode="general_knowledge",
                    query_outcome="no_match",
                    chat_outcome="no_match",
                ),
            )
            store.persist_response(
                tmp,
                response=response,
                request_messages=[ChatMessageItem(role="user", content="问题")],
                vault_id="test",
                vault_name="Test",
            )
            with self.assertRaises(UserInputError):
                store.to_source_document(tmp, response.session_id)

    def test_grounded_chat_extract_is_v2_and_keeps_provenance(self) -> None:
        store = ChatSessionStore()
        with tempfile.TemporaryDirectory() as tmp:
            response = ChatResponse(
                request_id="req_grounded",
                execution_id="exec_grounded",
                session_id="chat_grounded1234",
                session_revision=1,
                turn_id="turn_grounded",
                answer="有依据的回答。",
                answer_provenance=PROVENANCE,
            )
            store.persist_response(
                tmp,
                response=response,
                request_messages=[ChatMessageItem(role="user", content="问题")],
                vault_id="test",
                vault_name="Test",
            )
            document = store.to_source_document(tmp, response.session_id)

        self.assertIn('"schema_version": "knoarbor_chat_extract.v2"', document.content.text)
        self.assertIn('"mode": "knowledge_grounded"', document.content.text)


if __name__ == "__main__":
    unittest.main()
