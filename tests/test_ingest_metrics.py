from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knoarbor.pipelines.ingest_metrics import semantic_attempt_metrics


class IngestMetricsTests(unittest.TestCase):
    def test_semantic_attempt_metrics_use_run_event_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            events = Path(tmp_dir) / "run.events.jsonl"
            events.write_text(
                "\n".join(
                    [
                        '{"event_type":"model_call_started"}',
                        '{"event_type":"model_call_started"}',
                        '{"event_type":"model_call_finished"}',
                        '{"event_type":"model_output_invalid"}',
                        '{"event_type":"model_call_retrying"}',
                        '{"event_type":"model_call_failed"}',
                    ]
                ),
                encoding="utf-8",
            )

            metrics = semantic_attempt_metrics(events)

        self.assertEqual(
            metrics,
            {
                "attempted_call_count": 2,
                "response_call_count": 1,
                "failed_call_count": 1,
                "invalid_output_count": 1,
                "retry_count": 1,
                "observed_peak_in_flight": 2,
            },
        )

    def test_missing_event_authority_is_reported_as_unavailable(self) -> None:
        self.assertEqual(semantic_attempt_metrics(None), {})


if __name__ == "__main__":
    unittest.main()
