from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.audit.query_report import render_query_report
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.presenters.wiki_context import search_query

from tests.harness.snapshot import assert_json_snapshot


FIXTURE_DIR = Path(__file__).resolve().parent / "harness" / "fixtures" / "query"


class QueryGoldenTests(unittest.TestCase):
    def test_agent_loop_query_context_pack_matches_golden_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = _agent_loop_query_vault(Path(tmp_dir))

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="agent loop workflow",
                    mode="balanced",
                    max_results=4,
                    max_pages_to_read=4,
                    max_excerpts_per_page=2,
                    max_chars_per_excerpt=320,
                    max_context_chars=5000,
                    include_related=True,
                    record_query=False,
                )
            )

        snapshot = {
            "retrieval_mode": response.retrieval_mode,
            "results": [
                {
                    "path": result.path,
                    "title": result.title,
                    "relevance": result.relevance,
                    "match_kind": result.match_kind,
                    "matched_fields": result.matched_fields,
                    "excerpts": [
                        {
                            "path": excerpt.path,
                            "section": excerpt.section,
                            "content": excerpt.content,
                            "score": excerpt.score,
                        }
                        for excerpt in result.excerpts
                    ],
                }
                for result in response.results
            ],
            "trace": response.trace,
            "context_pack": response.context_pack,
        }
        assert_json_snapshot(self, snapshot, FIXTURE_DIR / "agent_loop_query_context.json")

    def test_query_report_markdown_matches_golden_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = _agent_loop_query_vault(Path(tmp_dir))
            request = WikiSearchRequest(
                vault_path=str(vault),
                query="agent loop workflow",
                mode="balanced",
                max_results=3,
                max_pages_to_read=3,
                max_excerpts_per_page=1,
                max_chars_per_excerpt=240,
                max_context_chars=4000,
                include_related=True,
                record_query=False,
            )
            response = search_query(request)

        report = render_query_report(request, response, "golden-query-run")
        report = re.sub(r"^- created_at: .+$", "- created_at: <normalized>", report, flags=re.MULTILINE)
        expected = (FIXTURE_DIR / "query_report.md").read_text(encoding="utf-8")
        self.assertEqual(report, expected)


def _agent_loop_query_vault(root: Path) -> Path:
    vault = root / "vaults" / "all"
    (vault / "wiki" / "pages").mkdir(parents=True)
    (vault / "wiki" / "sources").mkdir(parents=True)
    (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
        "---\n"
        "---\n\n"
        "# Agent Loop\n\n"
        "## Summary\n\n"
        "Agent loop is a control pattern where a model observes context, reasons, acts with tools, and uses feedback.\n\n"
        "## Claims\n\n"
        "- C1: Agent loops are dynamic and tool-aware.\n"
        "- C2: Workflows provide deterministic structure around uncertain agent decisions.\n\n"
        "## Entities\n\n"
        "- [[Agent Loop]]\n"
        "- [[Workflow]]\n"
        "- [[OpenClaw]]\n\n"
        "## Relations\n\n"
        "| Subject | Predicate | Object | Based on |\n"
        "|---|---|---|---|\n"
        "| [[Agent Loop]] | differs from | [[Workflow]] | C1 |\n"
        "| [[OpenClaw]] | implements | [[Agent Loop]] | C2 |\n\n"
        "## Synthesis\n\n"
        "Agent loop systems repeat observation, reasoning, action, and feedback. A workflow follows a predefined path, while an agent loop lets the model choose the next step.\n\n"
        "## Evidence\n\n"
        "| Claim | Source | Range | Basis | Confidence |\n"
        "|---|---|---|---|---|\n"
        "| C1 | sources/Agent-Loop-Source.md | unit:0 | Source supports agent loop behavior. | high |\n",
        encoding="utf-8",
    )
    (vault / "wiki" / "pages" / "OpenClaw.md").write_text(
        "---\n"
        "---\n\n"
        "# OpenClaw\n\n"
        "## Summary\n\n"
        "OpenClaw is an engineering agent system that combines structured workflows with agent loops.\n\n"
        "## Entities\n\n"
        "- [[OpenClaw]]\n"
        "- [[Agent Loop]]\n",
        encoding="utf-8",
    )
    (vault / "wiki" / "sources" / "Agent-Loop-Source.md").write_text(
        "---\n"
        "role: source_digest\n"
        "---\n\n"
        "# Agent Loop Source\n\n"
        "## Audit Summary\n\n"
        "Source digest for agent loop and workflow comparison notes.\n\n"
        "## Raw Source\n\n"
        "- raw/inbox/notes/agent-loop.md\n\n"
        "## Source Units\n\n"
        "- U1: Agent loop and workflow comparison notes.\n\n"
        "## Contribution Map\n\n"
        "- Agent-Loop.md: supports C1 and C2.\n",
        encoding="utf-8",
    )
    return vault


if __name__ == "__main__":
    unittest.main()
