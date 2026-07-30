from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest
from knoarbor.services.chat_agent import ChatAgentService
from knoarbor.services.chat_execution_safety import ChatExecutionSafety, ChatExecutionSafetyExceeded
from tests.helpers.chat_fakes import FakeChatClient, FakeServices, chat_answer_fixture


class ChatExecutionSafetyTest(unittest.TestCase):
    def test_envelope_counts_resources_without_candidate_limit(self) -> None:
        safety = ChatExecutionSafety(max_wall_seconds=60)
        safety.before_tool_call()
        safety.observe_tool_result({"candidates": [{"evidence_id": f"ev:{index}"} for index in range(100)]})
        safety.before_model_call(10**9)

        self.assertEqual(safety.tool_calls, 1)
        self.assertEqual(safety.model_calls, 1)
        self.assertGreater(safety.accumulated_bytes, 0)
        self.assertNotIn("max_provider_context_chars", safety.payload()["limits"])

    def test_wall_time_stop_is_typed_and_never_routes_general(self) -> None:
        safety = ChatExecutionSafety(max_wall_seconds=-1)
        client = FakeChatClient([])
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        tmp = workspace.name
        with patch(
            "knoarbor.services.chat_agent.ChatExecutionSafety",
            return_value=safety,
        ):
            response = ChatAgentService(client_factory=lambda _request: client).chat(
                ChatRequest(
                    message=ChatMessageItem(role="user", content="知识问题"),
                    vault_path=tmp,
                    append_ledger=False,
                ),
                FakeServices(),  # type: ignore[arg-type]
            )

        self.assertEqual(response.answer_provenance.query_outcome, "resource_exhausted")
        self.assertEqual(response.answer_provenance.chat_outcome, "resource_exhausted")
        self.assertEqual(response.answer_provenance.mode, "knowledge_gap")
        self.assertEqual(client.requests, [])
        self.assertIn("chat_execution_safety:wall_time", response.warnings)

    def test_wall_time_limit_reports_usage(self) -> None:
        safety = ChatExecutionSafety(max_wall_seconds=-1)
        with self.assertRaises(ChatExecutionSafetyExceeded) as raised:
            safety.before_model_call(100)
        self.assertEqual(raised.exception.reason, "wall_time")
        self.assertEqual(raised.exception.usage["model_calls"], 0)

    def test_gap_finishes_without_recursive_planning(self) -> None:
        safety = ChatExecutionSafety(max_wall_seconds=60)
        client = FakeChatClient([
            chat_answer_fixture(answer="Alpha 和 Beta 的通用解释。"),
        ])
        services = FakeServices()
        original_search = services.chat_knowledge.search_knowledge
        original_read = services.chat_knowledge.read_evidence
        search_arguments: list[dict[str, object]] = []
        read_arguments: list[dict[str, object]] = []

        def tracked_search(context, arguments):
            search_arguments.append(dict(arguments))
            return original_search(context, arguments)

        def tracked_read(context, arguments):
            read_arguments.append(dict(arguments))
            return original_read(context, arguments)

        services.chat_knowledge.search_knowledge = tracked_search  # type: ignore[method-assign]
        services.chat_knowledge.read_evidence = tracked_read  # type: ignore[method-assign]
        service = ChatAgentService(client_factory=lambda _request: client)
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        tmp = workspace.name
        with patch(
            "knoarbor.services.chat_agent.ChatExecutionSafety",
            return_value=safety,
        ):
            response = service.chat(
                ChatRequest(
                    message=ChatMessageItem(role="user", content="Alpha 和 Beta 分别如何工作？"),
                    vault_path=tmp,
                    append_ledger=False,
                ),
                services,  # type: ignore[arg-type]
            )

        self.assertEqual(response.answer_provenance.chat_outcome, "planning_exhausted")
        self.assertEqual(response.answer_provenance.mode, "general_knowledge")
        self.assertEqual(response.answer, "Alpha 和 Beta 的通用解释。")
        self.assertEqual(response.stats["retrieval_batch"]["status"], "candidates")
        self.assertEqual(len(search_arguments), 1)
        self.assertEqual(len(read_arguments), 1)
        self.assertEqual(response.stats["model_calls"], 3)


if __name__ == "__main__":
    unittest.main()
