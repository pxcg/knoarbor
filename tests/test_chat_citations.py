from __future__ import annotations

import unittest

from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem
from knoarbor.services.chat_reference_resolver import clean_answer_citation_paths, resolve_answer_presentation


class ChatCitationPolicyTests(unittest.TestCase):
    def test_returns_evidence_pack_pages_in_citation_order(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "primary_pages": [
                            {"path": "Agent-Loop.md", "title": "Agent Loop", "role": "primary"},
                        ],
                        "supporting_pages": [
                            {"path": "OpenClaw.md", "title": "OpenClaw", "role": "supporting"},
                        ],
                    }
                },
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="根据本地页面回答。")

        self.assertEqual([citation.path for citation in presentation.citations], ["Agent-Loop.md", "OpenClaw.md"])
        self.assertEqual(presentation.citations[0].role, "primary")
        self.assertEqual(presentation.citations[1].role, "supporting")

    def test_list_pages_is_navigation_not_public_citation_without_answer_refs(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="list_wiki_pages",
                citations=[
                    ChatCitation(kind="page", path="Agent-Loop.md", title="Agent Loop"),
                    ChatCitation(kind="page", path="Agent-Engineering.md", title="Agent Engineering"),
                ],
                result={"pages": []},
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="这些是相关页面列表。")

        self.assertEqual(presentation.citations, [])
        self.assertEqual(presentation.hidden_evidence_count, 2)

    def test_validates_model_selected_citations_against_trace(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="read_wiki_page",
                citations=[ChatCitation(kind="page", path="Agent-Loop.md", title="Trace Title")],
            )
        ]
        decision = [
            ChatCitation(kind="page", path="Agent-Loop.md", title="Model Title"),
            ChatCitation(kind="page", path="Not-Observed.md", title="Invalid"),
        ]

        presentation = resolve_answer_presentation(decision, trace, answer="结论来自本地页面。")

        self.assertEqual(len(presentation.citations), 1)
        self.assertEqual(presentation.citations[0].path, "Agent-Loop.md")
        self.assertEqual(presentation.citations[0].title, "Model Title")

    def test_answer_references_override_broad_model_selected_citations(self) -> None:
        citation_pages = [
            {"path": f"Page-{index}.md", "title": f"Page {index}", "role": "supporting"}
            for index in range(1, 21)
        ]
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={"evidence_pack": {"citation_pages": citation_pages}},
                citations=[ChatCitation(kind="page", path=page["path"], title=page["title"]) for page in citation_pages],
            )
        ]
        decision = [ChatCitation(kind="page", path=page["path"], title=page["title"]) for page in citation_pages]

        presentation = resolve_answer_presentation(decision, trace, answer="正文只明确引用 [1]、[2]、[3] 和 [4]。")

        self.assertEqual(len(presentation.citations), 4)
        self.assertEqual([citation.path for citation in presentation.citations], [f"Page-{index}.md" for index in range(1, 5)])
        self.assertEqual(presentation.hidden_evidence_count, 16)

    def test_answer_references_choose_matching_evidence_order(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "primary_pages": [
                            {"path": "A.md", "title": "A", "role": "primary"},
                            {"path": "B.md", "title": "B", "role": "primary"},
                        ]
                    }
                },
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="结论主要来自 [2]。")

        self.assertEqual(presentation.answer, "结论主要来自 [1]。")
        self.assertEqual([citation.path for citation in presentation.citations], ["B.md"])

    def test_answer_references_accept_fullwidth_brackets(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "citation_pages": [
                            {"path": "A.md", "title": "A", "role": "primary"},
                            {"path": "B.md", "title": "B", "role": "supporting"},
                        ]
                    }
                },
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="结论主要来自［2］。")

        self.assertEqual(presentation.answer, "结论主要来自[1]。")
        self.assertEqual([citation.path for citation in presentation.citations], ["B.md"])

    def test_sparse_answer_references_are_renumbered_with_filtered_citations(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "citation_pages": [
                            {"path": f"Page-{index}.md", "title": f"Page {index}", "role": "supporting"}
                            for index in range(1, 11)
                        ]
                    }
                },
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="核心依据是 [1]，辅助参考见 [7] 和［10］。")

        self.assertEqual(presentation.answer, "核心依据是 [1]，辅助参考见 [2] 和[3]。")
        self.assertEqual(
            [citation.path for citation in presentation.citations],
            ["Page-1.md", "Page-7.md", "Page-10.md"],
        )

    def test_query_evidence_without_answer_refs_keeps_answer_bearing_sources(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "citation_pages": [
                            {"path": f"Page-{index}.md", "title": f"Page {index}", "role": "supporting"}
                            for index in range(1, 7)
                        ]
                    }
                },
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="模型没有显式编号，但回答基于检索证据。")

        self.assertEqual(len(presentation.citations), 6)
        self.assertEqual(presentation.citations[4].path, "Page-5.md")
        self.assertEqual(presentation.citations[5].path, "Page-6.md")

    def test_list_pages_with_explicit_refs_can_become_public_citations(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="list_wiki_pages",
                citations=[
                    ChatCitation(kind="page", path=f"Page-{index}.md", title=f"Page {index}")
                    for index in range(1, 7)
                ],
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="可以先读 [1] 和 [6]。")

        self.assertEqual(presentation.answer, "可以先读 [1] 和 [2]。")
        self.assertEqual([citation.path for citation in presentation.citations], ["Page-1.md", "Page-6.md"])

    def test_read_wiki_page_single_page_answer_keeps_one_citation(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="read_wiki_page",
                citations=[ChatCitation(kind="page", path="Agent-Loop.md", title="Agent Loop")],
                result={"path": "Agent-Loop.md", "content": "Agent loop content."},
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="这个页面说明了 Agent Loop。")

        self.assertEqual(len(presentation.citations), 1)
        self.assertEqual(presentation.citations[0].path, "Agent-Loop.md")

    def test_clean_answer_paths_keeps_explicit_path_questions(self) -> None:
        citation = ChatCitation(kind="page", path="Agent-Loop.md", title="Agent Loop")

        self.assertIn(
            "Agent-Loop.md",
            clean_answer_citation_paths("见 Agent-Loop.md", [citation], latest_user_text="这个页面路径是什么？"),
        )
        self.assertNotIn(
            "Agent-Loop.md",
            clean_answer_citation_paths("见 Agent-Loop.md", [citation], latest_user_text="Agent Loop 是什么？"),
        )


if __name__ == "__main__":
    unittest.main()
