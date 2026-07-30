from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.storage.ledger import append_jsonl_ledger


class LedgerStorageTests(unittest.TestCase):
    def test_append_jsonl_ledger_writes_sorted_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            ledger = append_jsonl_ledger(vault, "maintenance/events.jsonl", {"b": 2, "a": 1})
            record = json.loads(ledger.read_text(encoding="utf-8"))

        self.assertEqual(record, {"a": 1, "b": 2})

    def test_append_jsonl_ledger_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(ValueError, "Invalid ledger path"):
                append_jsonl_ledger(Path(tmp_dir), "../events.jsonl", {"a": 1})


if __name__ == "__main__":
    unittest.main()
