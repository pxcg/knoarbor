import json
import unittest
from pathlib import Path


FIXTURE_PATH = Path("tests/fixtures/chat/agent_engineering_9turn.json")


class ChatEvalFixtureTests(unittest.TestCase):
    def test_agent_engineering_fixture_is_well_formed(self) -> None:
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(data["id"], "agent_engineering_openclaw_9turn")
        self.assertEqual(data["recommended_scope"], "all_vaults")

        turns = data["turns"]
        self.assertEqual(len(turns), 9)
        self.assertEqual([turn["turn"] for turn in turns], list(range(1, 10)))

        for turn in turns:
            self.assertTrue(turn["question"].strip())
            for page in turn.get("expected_pages", []):
                self.assertRegex(page, r"^(concepts|sources|entities|comparisons|workflows|queries)/.+\.md$")

        final_turn = turns[-1]
        self.assertEqual(final_turn["expected_pages"], [])
        self.assertGreaterEqual(len(final_turn["expected_behavior"]), 3)
        self.assertTrue(
            any("reuse prior conversation context" in item for item in final_turn["expected_behavior"])
        )


if __name__ == "__main__":
    unittest.main()
