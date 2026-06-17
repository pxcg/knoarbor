from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path("scripts/eval/weknora_rag_baseline.py")


def load_module():
    spec = importlib.util.spec_from_file_location("weknora_rag_baseline", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeKnoraRagBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_load_fixture_reads_turns_and_expected_pages(self) -> None:
        fixture = self.module.load_fixture(Path("tests/fixtures/chat/agent_architecture_6turn_mixed.json"))

        self.assertEqual(fixture.id, "agent_architecture_6turn_mixed")
        self.assertEqual(len(fixture.turns), 6)
        self.assertEqual(fixture.turns[0].turn, 1)
        self.assertIn("sources/Agent-Loop-Source.md", fixture.turns[0].expected_pages)

    def test_parse_sse_lines_supports_answer_and_reference_events(self) -> None:
        lines = [
            "event: message",
            'data: {"response_type":"answer","content":"Agent"}',
            "",
            "event: message",
            (
                'data: {"response_type":"references","knowledge_references":['
                '{"id":"chunk-1","knowledge_title":"Agent.md","chunk_index":0,"score":0.1}'
                "]}"
            ),
            "",
        ]

        events = self.module.parse_sse_lines(lines)

        self.assertEqual(events[0]["response_type"], "answer")
        self.assertEqual(events[0]["content"], "Agent")
        self.assertEqual(events[1]["knowledge_references"][0]["knowledge_title"], "Agent.md")

    def test_collect_references_deduplicates_chunks(self) -> None:
        events = [
            {
                "knowledge_references": [
                    {"id": "a", "knowledge_title": "A", "chunk_index": 0},
                    {"id": "a", "knowledge_title": "A", "chunk_index": 0},
                ]
            },
            {"knowledge_references": [{"id": "b", "knowledge_title": "B", "chunk_index": 1}]},
        ]

        references = self.module.collect_references(events)

        self.assertEqual([item["id"] for item in references], ["a", "b"])

    def test_build_report_includes_reference_count_and_expected_pages(self) -> None:
        fixture = self.module.load_fixture(Path("tests/fixtures/chat/agent_architecture_6turn_mixed.json"))
        report = self.module.build_report(
            fixture=fixture,
            run_metadata={
                "base_url": "http://127.0.0.1:8080",
                "knowledge_base_id": "kb",
                "session_id": "session",
                "started_at": "2026-06-17T00:00:00",
                "finished_at": "2026-06-17T00:00:01",
                "elapsed_seconds": 1,
            },
            turn_results=[
                {
                    "turn": 1,
                    "question": "Agent Loop 是什么？",
                    "expected_pages": ["concepts/Agent-Loop-and-Control-Patterns.md"],
                    "answer": "Agent Loop answer",
                    "elapsed_seconds": 1,
                    "event_count": 2,
                    "references": [{"knowledge_title": "Agent.md", "chunk_index": 0, "score": 0.1, "content": "chunk text"}],
                }
            ],
        )

        self.assertIn("reference_count: 1", report)
        self.assertIn("concepts/Agent-Loop-and-Control-Patterns.md", report)
        self.assertIn("Agent.md", report)


if __name__ == "__main__":
    unittest.main()
