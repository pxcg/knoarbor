from __future__ import annotations

import unittest

from knoarbor.audit.ingest_report import render_ingest_report


class IngestReportTests(unittest.TestCase):
    def test_renders_write_gate_and_semantic_review_separately(self) -> None:
        report = render_ingest_report(
            {
                "run_id": "run-1",
                "started_at": "2026-06-24 10:00:00",
                "finished_at": "2026-06-24 10:01:00",
                "stats": {
                    "source_count": 1,
                    "processed_count": 1,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "written_count": 1,
                    "segment_count": 1,
                    "failed_segment_count": 0,
                    "max_segment_chars": 128,
                    "recovery_candidate_count": 0,
                    "effective_max_concurrent_sources": 1,
                    "configured_max_concurrent_sources": 1,
                },
                "metrics": {"elapsed_seconds": 1.0, "semantic": {"semantic_call_count": 0, "total_tokens": 0}},
                "document_processing": {"stats": {}},
                "quality_trend": {},
                "sources": [
                    {
                        "connector": "markdown",
                        "source_id": "source-1",
                        "source_file": "raw/notes/a2a.md",
                        "should_process": True,
                        "mode": "new_source",
                        "reason": "test",
                        "status": "written",
                        "wrote": True,
                        "redaction": {},
                        "context": {
                            "review_policy": {
                                "should_review": True,
                                "triggers": ["update"],
                                "reasons": ["operation 1 updates Agent.md."],
                            }
                        },
                        "write_gate": {
                            "passed": False,
                            "approved_operation_indexes": [],
                            "issues": [
                                {
                                    "operation_index": 1,
                                    "code": "missing_evidence",
                                    "message": "Non-source drafts must include explicit evidence rows.",
                                }
                            ],
                        },
                        "checkpoint": {},
                        "touched_pages": [],
                        "scoped_lint_result": {},
                        "approved_operation_indexes": [],
                        "generated_pages": ["Agent.md"],
                        "metrics": {"elapsed_seconds": 1.0, "semantic": {"semantic_call_count": 0, "total_tokens": 0}},
                        "segmentation": {"mode": "none", "segment_count": 1},
                        "segments": [],
                        "page_plan_operations": [],
                        "draft_atom_traces": [],
                        "review_decisions": [
                            {
                                "operation_index": 1,
                                "decision": "reject",
                                "quality_score": 0.4,
                                "risk_level": "high",
                                "write_safety": "reject",
                                "reason": "Missing evidence.",
                            }
                        ],
                        "warnings": [],
                    }
                ],
                "lifecycle_candidates": [],
            }
        )

        self.assertIn("Write gate:", report)
        self.assertIn("`missing_evidence`", report)
        self.assertIn("Semantic review:", report)
        self.assertIn("triggers: update", report)
        self.assertIn("reject / reject / risk=high", report)


if __name__ == "__main__":
    unittest.main()
