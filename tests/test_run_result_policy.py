from __future__ import annotations

import unittest

from knoarbor.runtime.result_policy import completion_status_for_result


class RunResultPolicyTests(unittest.TestCase):
    def test_ingest_failures_mark_partial_completion(self) -> None:
        status = completion_status_for_result(
            "ingest",
            {
                "stats": {
                    "source_count": 3,
                    "processed_count": 2,
                    "failed_count": 1,
                }
            },
        )

        self.assertEqual(status, "partially_failed")

    def test_lint_failed_repair_marks_partial_completion(self) -> None:
        status = completion_status_for_result(
            "lint",
            {
                "repair_results": [
                    {"status": "completed"},
                    {"status": "failed"},
                ]
            },
        )

        self.assertEqual(status, "partially_failed")

    def test_query_gaps_do_not_change_run_completion(self) -> None:
        status = completion_status_for_result("query", {"gaps": ["No result"]})

        self.assertEqual(status, "completed")


if __name__ == "__main__":
    unittest.main()
