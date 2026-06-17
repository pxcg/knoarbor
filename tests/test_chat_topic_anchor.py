from __future__ import annotations

import tempfile
import unittest

from knoarbor.core.schemas.chat import ChatMessageItem, ChatResponse
from knoarbor.services.chat_sessions import ChatSessionStore
from knoarbor.services.chat_topic_anchor import ChatTopicAnchorBuilder


class ChatTopicAnchorTest(unittest.TestCase):
    def test_first_turn_starts_new_topic(self) -> None:
        anchor = ChatTopicAnchorBuilder().build("Agent Loop 是什么？")

        self.assertEqual(anchor.relation_to_previous, "switch")
        self.assertIn("Agent Loop", anchor.active_topic)
        self.assertIn("Agent Loop", anchor.key_entities)

    def test_followup_keeps_existing_topic(self) -> None:
        store = ChatSessionStore()
        first_response = ChatResponse(
            session_id="chat_anchor1234",
            answer="Agent Loop 是推理、行动和观察循环。",
            messages=[
                ChatMessageItem(role="user", content="Agent Loop 是什么？"),
                ChatMessageItem(role="assistant", content="Agent Loop 是推理、行动和观察循环。"),
            ],
            topic_anchor=ChatTopicAnchorBuilder().build("Agent Loop 是什么？"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            session = store.persist_response(tmp, response=first_response, request_messages=first_response.messages, vault_id="test", vault_name="Test")
            anchor = ChatTopicAnchorBuilder().build("那它和 Workflow 有什么区别？", existing_session=session)

        self.assertEqual(anchor.relation_to_previous, "continue")
        self.assertEqual(anchor.active_topic, "Agent Loop")
        self.assertIn("Workflow", anchor.key_entities)

    def test_synthesis_followup_preserves_goal(self) -> None:
        prior = ChatTopicAnchorBuilder().build("帮我设计一个生产级 Agent 系统架构，包含工具、记忆、路由和监控")
        with tempfile.TemporaryDirectory() as tmp:
            session = ChatSessionStore().persist_response(
                tmp,
                response=ChatResponse(
                    session_id="chat_anchor5678",
                    answer="方案回答。",
                    messages=[
                        ChatMessageItem(role="user", content="帮我设计一个生产级 Agent 系统架构，包含工具、记忆、路由和监控"),
                        ChatMessageItem(role="assistant", content="方案回答。"),
                    ],
                    topic_anchor=prior,
                ),
                request_messages=[],
                vault_id="test",
                vault_name="Test",
            )

            anchor = ChatTopicAnchorBuilder().build("最后，把前面内容整理成技术设计文档大纲。", existing_session=session)

        self.assertEqual(anchor.relation_to_previous, "synthesize")
        self.assertEqual(anchor.active_topic, prior.active_topic)
        self.assertEqual(anchor.active_goal, prior.active_goal)

    def test_unrelated_question_switches_topic(self) -> None:
        prior = ChatTopicAnchorBuilder().build("Agent Loop 是什么？")
        with tempfile.TemporaryDirectory() as tmp:
            session = ChatSessionStore().persist_response(
                tmp,
                response=ChatResponse(
                    session_id="chat_anchor9012",
                    answer="Agent Loop 回答。",
                    messages=[
                        ChatMessageItem(role="user", content="Agent Loop 是什么？"),
                        ChatMessageItem(role="assistant", content="Agent Loop 回答。"),
                    ],
                    topic_anchor=prior,
                ),
                request_messages=[],
                vault_id="test",
                vault_name="Test",
            )

            anchor = ChatTopicAnchorBuilder().build("iOS 音频模型部署应该怎么做？", existing_session=session)

        self.assertEqual(anchor.relation_to_previous, "switch")
        self.assertIn("iOS", anchor.active_topic)
        self.assertNotEqual(anchor.active_topic, prior.active_topic)


if __name__ == "__main__":
    unittest.main()
