from __future__ import annotations

import unittest

from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem
from knoarbor.services.chat_reference_resolver import clean_answer_citation_paths, resolve_answer_presentation


class ChatCitationPolicyTests(unittest.TestCase):
    def test_raw_evidence_citation_numbers_resolve_to_source_units(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "citation_evidence": [
                            {
                                "index": index,
                                "kind": "source_unit",
                                "evidence_id": f"ev:{index}",
                                "source_unit_id": f"unit:{index}",
                                "source_path": "/vault/raw/source.md",
                                "title": f"Section {index}",
                            }
                            for index in range(1, 5)
                        ],
                        "citation_pages": [{"path": "Topic.md", "title": "Topic", "role": "primary"}],
                    }
                },
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="架构见 [1][2]，流程见 [3][4]。")

        self.assertEqual(presentation.warnings, [])
        self.assertEqual([citation.kind for citation in presentation.citations], ["raw_evidence"] * 4)
        self.assertEqual([citation.source_unit_id for citation in presentation.citations], [f"unit:{index}" for index in range(1, 5)])

    def test_global_evidence_markers_resolve_across_multiple_tool_batches(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                result={
                    "raw_evidence": [
                        {"evidence_id": "ev:1", "source_unit_id": "unit:1", "source_path": "raw/a.md", "title": "First"},
                        {"evidence_id": "ev:2", "source_unit_id": "unit:2", "source_path": "raw/a.md", "title": "Second"},
                    ]
                },
            ),
            ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                result={
                    "raw_evidence": [
                        {"evidence_id": "ev:2", "source_unit_id": "unit:2", "source_path": "raw/a.md", "title": "Second"},
                        {"evidence_id": "ev:3", "source_unit_id": "unit:3", "source_path": "raw/a.md", "title": "Third"},
                    ]
                },
            ),
        ]

        presentation = resolve_answer_presentation([], trace, answer="第三项见 [3]，第一项见 [1]。")

        self.assertEqual(presentation.answer, "第三项见 [1]，第一项见 [2]。")
        self.assertEqual([citation.source_unit_id for citation in presentation.citations], ["unit:3", "unit:1"])
        self.assertEqual(presentation.hidden_evidence_count, 1)

    def test_returns_canonical_evidence_pack_pages_in_citation_order(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "citation_pages": [
                            {"path": "Agent-Loop.md", "title": "Agent Loop", "role": "primary"},
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

    def test_validated_support_span_overrides_retrieval_match_span(self) -> None:
        trace = [ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            citations=[ChatCitation(
                kind="raw_evidence",
                evidence_id="ev:1",
                source_unit_id="unit:1",
                raw_revision_id="rawrev:1",
                char_start=10,
                char_end=20,
            )],
            result={"raw_evidence": [{"evidence_id": "ev:1", "source_unit_id": "unit:1", "char_start": 10, "char_end": 20}]},
        )]
        decision = [ChatCitation(
            kind="raw_evidence",
            evidence_id="ev:1",
            source_unit_id="unit:1",
            raw_revision_id="rawrev:1",
            char_start=103,
            char_end=118,
        )]

        presentation = resolve_answer_presentation(decision, trace, answer="结论来自原文 [1]。")

        self.assertEqual((presentation.citations[0].char_start, presentation.citations[0].char_end), (103, 118))

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

    def test_reference_parser_accepts_three_digit_markers(self) -> None:
        pages = [
            {"path": f"Page-{index}.md", "title": f"Page {index}"}
            for index in range(1, 121)
        ]
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={"evidence_pack": {"citation_pages": pages}},
            )
        ]

        presentation = resolve_answer_presentation(
            [],
            trace,
            answer="依据见 [120]。",
        )

        self.assertEqual(presentation.answer, "依据见 [1]。")
        self.assertEqual(
            [citation.path for citation in presentation.citations],
            ["Page-120.md"],
        )

    def test_answer_references_choose_matching_evidence_order(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={
                    "evidence_pack": {
                        "citation_pages": [
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

    def test_read_evidence_single_source_answer_keeps_one_citation(self) -> None:
        trace = [
            ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                citations=[ChatCitation(kind="raw_evidence", path="raw/agent-loop.md", title="Agent Loop", evidence_id="ev:1", source_unit_id="unit:1")],
                result={"raw_evidence": [{"evidence_id": "ev:1", "source_unit_id": "unit:1", "content": "Agent loop content."}]},
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="原始材料说明了 Agent Loop [1]。")

        self.assertEqual(len(presentation.citations), 1)
        self.assertEqual(presentation.citations[0].path, "raw/agent-loop.md")

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
