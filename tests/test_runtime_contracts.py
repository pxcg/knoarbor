from __future__ import annotations

import unittest

from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem
from knoarbor.core.schemas.wiki_query import WIKI_ANSWER_PAGE_ROLES, WIKI_QUERY_RESPONSE_FIELDS, WIKI_QUERY_SCHEMA_VERSION
from knoarbor.audit.contracts import LEDGER_PATHS, LEDGER_SCHEMA_VERSIONS, REPORT_DIRECTORIES, REPORT_KINDS
from knoarbor.pipelines.ingest_observer import INGEST_OBSERVATION_EVENT_TYPES, INGEST_OBSERVATION_STEPS
from knoarbor.services.chat_evidence import CHAT_EVIDENCE_PACK_KEYS, CHAT_EVIDENCE_PACK_SCHEMA_VERSION, ChatEvidencePlanner
from knoarbor.services.chat_reference_resolver import resolve_answer_presentation


class RuntimeContractTests(unittest.TestCase):
    def test_ingest_observation_steps_are_stable_ordered_contract(self) -> None:
        self.assertEqual(
            INGEST_OBSERVATION_STEPS,
            (
                "input",
                "segment",
                "normalize_agent",
                "atom_agent",
                "retrieval",
                "plan_agent",
                "draft_agent",
                "review_agent",
                "write_gate",
                "write",
            ),
        )
        self.assertEqual(
            INGEST_OBSERVATION_EVENT_TYPES,
            ("ingest_step_started", "ingest_step_finished", "ingest_step_skipped"),
        )

    def test_query_response_contract_names_answer_set_surfaces(self) -> None:
        self.assertEqual(WIKI_QUERY_SCHEMA_VERSION, "wiki_query.v1")
        self.assertEqual(WIKI_ANSWER_PAGE_ROLES, ("primary", "supporting", "source"))
        for field_name in (
            "results",
            "primary_pages",
            "supporting_pages",
            "source_pages",
            "answer_scope",
            "answer_set",
            "evidence_coverage",
            "context_pack",
        ):
            self.assertIn(field_name, WIKI_QUERY_RESPONSE_FIELDS)

    def test_chat_evidence_pack_keeps_candidate_evidence_separate_from_public_citations(self) -> None:
        pack = ChatEvidencePlanner().build_search_pack(
            query="Agent Loop 是什么？",
            result_count=3,
            answer_scope={"kind": "narrow"},
            answer_set={
                "kind": "multi_page",
                "primary_paths": ["Agent-Loop.md"],
                "supporting_paths": ["Memory.md"],
                "source_paths": ["sources/Agent-Loop-Source.md"],
            },
            evidence_coverage={"status": "strong", "primary_count": 1, "supporting_count": 1, "source_count": 1},
            primary_page={"path": "Agent-Loop.md", "title": "Agent Loop", "summary": "Loop page.", "content": "Loop content."},
            primary_pages=[{"path": "Agent-Loop.md", "title": "Agent Loop", "summary": "Loop page.", "content": "Loop content."}],
            supporting_pages=[{"path": "Memory.md", "title": "Memory", "summary": "Memory page.", "content": "Memory content."}],
            source_pages=[{"path": "sources/Agent-Loop-Source.md", "title": "Agent Loop Source", "summary": "Source audit."}],
            results=[
                {"path": "Agent-Loop.md", "title": "Agent Loop"},
                {"path": "Memory.md", "title": "Memory"},
                {"path": "Extra.md", "title": "Extra"},
            ],
            warnings=[],
        ).payload

        self.assertEqual(pack["schema_version"], CHAT_EVIDENCE_PACK_SCHEMA_VERSION)
        for key in CHAT_EVIDENCE_PACK_KEYS:
            self.assertIn(key, pack)
        self.assertEqual([page["path"] for page in pack["citation_pages"]], ["Agent-Loop.md", "Memory.md", "sources/Agent-Loop-Source.md"])
        self.assertEqual([page["path"] for page in pack["further_results"]], ["Extra.md"])

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
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["query"], "query_record.v1")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["query_feedback"], "query_feedback.v1")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["token"], "token_ledger.v1")
        self.assertEqual(LEDGER_SCHEMA_VERSIONS["run_failure"], "run_failure_record.v1")


if __name__ == "__main__":
    unittest.main()
