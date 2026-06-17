from __future__ import annotations

import unittest

from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem
from knoarbor.services.chat_citations import clean_answer_citation_paths, final_citations


class ChatCitationPolicyTests(unittest.TestCase):
    def test_returns_evidence_pack_pages_in_citation_order(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "primary_pages": [
                            {"path": "concepts/Agent-Loop.md", "title": "Agent Loop", "role": "primary"},
                        ],
                        "supporting_pages": [
                            {"path": "entities/OpenClaw.md", "title": "OpenClaw", "role": "supporting"},
                        ],
                    }
                },
            )
        ]

        citations = final_citations([], trace)

        self.assertEqual([citation.path for citation in citations], ["concepts/Agent-Loop.md", "entities/OpenClaw.md"])
        self.assertEqual(citations[0].role, "primary")
        self.assertEqual(citations[1].role, "supporting")

    def test_uses_page_tool_citations_when_no_evidence_pack_exists(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="list_wiki_pages",
                citations=[
                    ChatCitation(kind="page", path="concepts/Agent-Loop.md", title="Agent Loop"),
                    ChatCitation(kind="page", path="concepts/Agent-Engineering.md", title="Agent Engineering"),
                ],
                result={"pages": []},
            )
        ]

        citations = final_citations([], trace)

        self.assertEqual([citation.path for citation in citations], ["concepts/Agent-Loop.md", "concepts/Agent-Engineering.md"])

    def test_validates_model_selected_citations_against_trace(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="read_wiki_page",
                citations=[ChatCitation(kind="page", path="concepts/Agent-Loop.md", title="Trace Title")],
            )
        ]
        decision = [
            ChatCitation(kind="page", path="concepts/Agent-Loop.md", title="Model Title"),
            ChatCitation(kind="page", path="concepts/Not-Observed.md", title="Invalid"),
        ]

        citations = final_citations(decision, trace)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].path, "concepts/Agent-Loop.md")
        self.assertEqual(citations[0].title, "Model Title")

    def test_answer_references_choose_matching_evidence_order(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "primary_pages": [
                            {"path": "concepts/A.md", "title": "A", "role": "primary"},
                            {"path": "concepts/B.md", "title": "B", "role": "primary"},
                        ]
                    }
                },
            )
        ]

        citations = final_citations([], trace, answer="结论主要来自 [2]。")

        self.assertEqual([citation.path for citation in citations], ["concepts/B.md"])

    def test_keeps_more_than_four_evidence_citations_for_inline_rendering(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "citation_pages": [
                            {"path": f"concepts/Page-{index}.md", "title": f"Page {index}", "role": "supporting"}
                            for index in range(1, 7)
                        ]
                    }
                },
            )
        ]

        citations = final_citations([], trace)

        self.assertEqual(len(citations), 6)
        self.assertEqual(citations[4].path, "concepts/Page-5.md")
        self.assertEqual(citations[5].path, "concepts/Page-6.md")

    def test_keeps_more_than_four_trace_citations_without_evidence_pack(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="list_wiki_pages",
                citations=[
                    ChatCitation(kind="page", path=f"concepts/Page-{index}.md", title=f"Page {index}")
                    for index in range(1, 7)
                ],
            )
        ]

        citations = final_citations([], trace)

        self.assertEqual(len(citations), 6)
        self.assertEqual(citations[-1].path, "concepts/Page-6.md")

    def test_clean_answer_paths_keeps_explicit_path_questions(self) -> None:
        citation = ChatCitation(kind="page", path="concepts/Agent-Loop.md", title="Agent Loop")

        self.assertIn(
            "concepts/Agent-Loop.md",
            clean_answer_citation_paths("见 concepts/Agent-Loop.md", [citation], latest_user_text="这个页面路径是什么？"),
        )
        self.assertNotIn(
            "concepts/Agent-Loop.md",
            clean_answer_citation_paths("见 concepts/Agent-Loop.md", [citation], latest_user_text="Agent Loop 是什么？"),
        )


if __name__ == "__main__":
    unittest.main()
