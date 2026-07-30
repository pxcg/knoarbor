from __future__ import annotations

import unittest

from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem
from knoarbor.core.schemas.wiki_query import (
    WIKI_QUERY_RESPONSE_FIELDS,
    WIKI_QUERY_SCHEMA_VERSION,
    WikiSearchRequest,
    WikiSearchResult,
)
from knoarbor.audit.contracts import LEDGER_PATHS, LEDGER_SCHEMA_VERSIONS, REPORT_DIRECTORIES, REPORT_KINDS
from knoarbor.services.chat_evidence import CHAT_EVIDENCE_PACK_KEYS, CHAT_EVIDENCE_PACK_SCHEMA_VERSION, ChatEvidencePlanner
from knoarbor.services.chat_reference_resolver import resolve_answer_presentation


class RuntimeContractTests(unittest.TestCase):
    def test_query_response_contract_has_one_locator_and_evidence_surface(self) -> None:
        self.assertEqual(WIKI_QUERY_SCHEMA_VERSION, "wiki_query.v4")
        for field_name in (
            "results",
            "status",
            "evidence_handles",
            "raw_evidence",
            "context_pack",
        ):
            self.assertIn(field_name, WIKI_QUERY_RESPONSE_FIELDS)
        for removed in (
            "primary_pages",
            "supporting_pages",
            "source_pages",
            "answer_scope",
            "answer_set",
            "evidence_coverage",
            "response_guidance",
            "gap_suggestions",
            "relation_paths",
        ):
            self.assertNotIn(removed, WIKI_QUERY_RESPONSE_FIELDS)

    def test_query_contract_exposes_no_retired_page_retrieval_controls(self) -> None:
        for removed in ("page_dirs", "page_roles", "include_related", "include_content"):
            self.assertNotIn(removed, WikiSearchRequest.model_fields)

    def test_query_locator_contract_contains_no_page_content_projection(self) -> None:
        for removed in (
            "page_role",
            "match_kind",
            "summary",
            "claims",
            "excerpts",
            "content",
            "source",
            "entities",
            "outbound_links",
            "content_truncated",
        ):
            self.assertNotIn(removed, WikiSearchResult.model_fields)

    def test_chat_evidence_pack_keeps_candidate_evidence_separate_from_public_citations(self) -> None:
        projection = ChatEvidencePlanner().project_tool_observation(
            "retrieve_knowledge_batch",
            "ok",
            "read",
            {"raw_evidence": [{"evidence_id": "ev:1", "source_unit_id": "unit:1", "content": "fact"}]},
        )
        pack = projection["evidence_pack"]

        self.assertEqual(pack["schema_version"], CHAT_EVIDENCE_PACK_SCHEMA_VERSION)
        for key in CHAT_EVIDENCE_PACK_KEYS:
            self.assertIn(key, pack)
        self.assertEqual(pack["citation_evidence"][0]["evidence_id"], "ev:1")
        self.assertEqual(pack["citation_evidence"][0]["citation_marker"], "[1]")

    def test_chat_answer_evidence_uses_one_global_deduplicated_namespace(self) -> None:
        observations = [
            ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                result={
                    "raw_evidence": [
                        {"evidence_id": "ev:1", "source_unit_id": "unit:1", "content": "first"},
                        {"evidence_id": "ev:2", "source_unit_id": "unit:2", "content": "second"},
                    ]
                },
            ),
            ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                result={
                    "raw_evidence": [
                        {"evidence_id": "ev:2", "source_unit_id": "unit:2", "content": "second"},
                        {"evidence_id": "ev:3", "source_unit_id": "unit:3", "content": "third"},
                    ]
                },
            ),
        ]

        projected = ChatEvidencePlanner().project_answer_observations(observations)
        pack = projected[0]["evidence_pack"]

        self.assertEqual(
            [item["index"] for item in pack["raw_evidence"]],
            [1, 2, 3],
        )
        self.assertTrue(
            all("evidence_id" not in item for item in pack["raw_evidence"])
        )
        self.assertEqual(
            [
                item["support_spans"][0]["text"]
                for item in pack["raw_evidence"]
            ],
            ["first", "second", "third"],
        )
        self.assertTrue(all("citation_marker" not in item for item in pack["raw_evidence"]))
        self.assertTrue(all(item["support_spans"] for item in pack["raw_evidence"]))

    def test_chat_answer_evidence_keeps_distinct_spans_from_one_source_unit(self) -> None:
        observations = [
            ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                result={
                    "raw_evidence": [
                        {
                            "evidence_id": "evref:color",
                            "source_evidence_id": "ev:unit",
                            "source_unit_id": "unit:aurora",
                            "excerpt": "Green is the most common aurora color.",
                            "content": "Green is the most common aurora color. Auroras are common near the Arctic Circle.",
                        },
                        {
                            "evidence_id": "evref:location",
                            "source_evidence_id": "ev:unit",
                            "source_unit_id": "unit:aurora",
                            "excerpt": "Auroras are common near the Arctic Circle.",
                            "content": "Green is the most common aurora color. Auroras are common near the Arctic Circle.",
                        },
                    ]
                },
            )
        ]

        projected = ChatEvidencePlanner().project_answer_observations(observations)
        pack = projected[0]["evidence_pack"]

        self.assertTrue(all("citation_marker" not in item for item in pack["raw_evidence"]))
        self.assertTrue(all("excerpt" not in item for item in pack["raw_evidence"]))
        self.assertTrue(all("content" not in item for item in pack["raw_evidence"]))
        self.assertTrue(all(item["support_spans"] for item in pack["raw_evidence"]))

    def test_chat_reference_resolver_publishes_only_answer_referenced_evidence(self) -> None:
        citation_pages = [
            {"path": f"Page-{index}.md", "title": f"Page {index}", "role": "supporting"}
            for index in range(1, 8)
        ]
        trace = [
            ChatToolTraceItem(
                tool="query_wiki",
                result={"evidence_pack": {"citation_pages": citation_pages}},
                citations=[ChatCitation(kind="page", path=page["path"], title=page["title"]) for page in citation_pages],
            )
        ]

        presentation = resolve_answer_presentation([], trace, answer="回答正文使用 [1] 和 [7]。")

        self.assertEqual(presentation.answer, "回答正文使用 [1] 和 [2]。")
        self.assertEqual([citation.path for citation in presentation.citations], ["Page-1.md", "Page-7.md"])
        self.assertEqual(presentation.hidden_evidence_count, 5)

    def test_report_and_ledger_contract_paths_are_stable(self) -> None:
        self.assertEqual(REPORT_KINDS, ("ingest", "lint", "query", "run-failure"))
        self.assertEqual(REPORT_DIRECTORIES["ingest"], "maintenance/reports/ingest")
        self.assertEqual(REPORT_DIRECTORIES["lint"], "maintenance/reports/lint")
        self.assertEqual(REPORT_DIRECTORIES["query"], "maintenance/reports/query")
        self.assertEqual(REPORT_DIRECTORIES["run-failure"], "maintenance/reports/run-failure")
        self.assertEqual(LEDGER_PATHS["ingest"], ".knoarbor/ledgers/ingest.jsonl")
        self.assertEqual(LEDGER_PATHS["lint"], ".knoarbor/ledgers/lint_run.jsonl")
        self.assertEqual(LEDGER_PATHS["query"], ".knoarbor/ledgers/query.jsonl")
        self.assertEqual(LEDGER_PATHS["token"], ".knoarbor/ledgers/token.jsonl")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["ingest"], "ingest_run.v1")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["lint"], "lint_run_record.v1")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["query"], "query_record.v2")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["query_feedback"], "query_feedback.v1")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["token"], "token_ledger.v1")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["run_failure"], "run_failure_record.v1")


if __name__ == "__main__":
    unittest.main()
