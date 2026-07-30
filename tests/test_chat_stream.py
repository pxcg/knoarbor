from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import patch

from knoarbor.core.schemas.chat import ChatEvent, ChatRequest
from knoarbor.core.errors import ExternalServiceError, ModelOutputError
from knoarbor.services.chat_stream import chat_event_payload, chat_event_stream, stream_exception_payload


class ChatStreamEventTest(unittest.TestCase):
    def test_stream_error_preserves_structured_code_category_and_stage(self) -> None:
        retrieval = stream_exception_payload(
            ExternalServiceError("embedding endpoint timed out"),
            stage="retrieving",
        )
        invalid_output = stream_exception_payload(
            ModelOutputError("invalid structured answer"),
            stage="generating",
        )

        self.assertEqual(retrieval["error"]["code"], "KA-EXT-001")
        self.assertEqual(retrieval["error"]["category"], "external_service_error")
        self.assertEqual(retrieval["error"]["stage"], "retrieving")
        self.assertTrue(retrieval["error"]["retryable"])
        self.assertEqual(invalid_output["error"]["code"], "KA-MODEL-001")
        self.assertEqual(invalid_output["error"]["stage"], "generating")

    def test_provisional_answer_source_has_its_own_stream_event(self) -> None:
        payload = chat_event_payload(
            ChatEvent(
                event_type="answer_source_selected",
                created_at="2026-07-17T00:00:00Z",
                payload={
                    "source_path": "model_general",
                    "provisional": True,
                },
            )
        )

        self.assertEqual(payload["event"], "source")
        self.assertEqual(payload["stage"], "generating")
        self.assertEqual(payload["payload"]["source_path"], "model_general")
        self.assertTrue(payload["payload"]["provisional"])

    def test_answer_decision_and_composer_phases_remain_generating(self) -> None:
        for phase in ("answer_decision", "response_composer"):
            payload = chat_event_payload(
                ChatEvent(
                    event_type="model_call_started",
                    created_at="2026-07-17T00:00:00Z",
                    payload={"phase": "answer", "semantic_phase": phase},
                )
            )
            self.assertEqual(payload["stage"], "generating")

    def test_stream_emits_heartbeat_while_chat_has_no_events(self) -> None:
        class BlockingChat:
            def chat(self, *_args, **_kwargs):
                time.sleep(0.05)
                raise RuntimeError("finished after heartbeat")

        class Services:
            chat = BlockingChat()

        async def first_chunk() -> str:
            stream = chat_event_stream(
                ChatRequest(
                    schema_version="chat_request.v4",
                    request_id="req_test",
                    execution_id="exec_test",
                    vault_path="/tmp/test-vault",
                    message={"message_id": "msg_test", "role": "user", "content": "test"},
                ),
                Services(),
            )
            try:
                return await anext(stream)
            finally:
                await stream.aclose()

        with patch("knoarbor.services.chat_stream.CHAT_STREAM_HEARTBEAT_SECONDS", 0.01):
            self.assertEqual(asyncio.run(first_chunk()), ": keep-alive\n\n")


if __name__ == "__main__":
    unittest.main()
