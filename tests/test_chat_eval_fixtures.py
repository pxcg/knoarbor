import json
import unittest
from pathlib import Path


MAIN_FIXTURE_PATH = Path("tests/fixtures/chat/agent_architecture_6turn_mixed.json")
IOS_AUDIO_FIXTURE_PATH = Path("tests/fixtures/chat/ios_audio_tennis_detection_6turn.json")
ARCHIVED_FIXTURE_PATH = Path("tests/fixtures/chat/archive/agent_engineering_openclaw_9turn.json")


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_turns_well_formed(testcase: unittest.TestCase, data: dict, expected_count: int) -> None:
    turns = data["turns"]
    testcase.assertEqual(len(turns), expected_count)
    testcase.assertEqual([turn["turn"] for turn in turns], list(range(1, expected_count + 1)))

    for turn in turns:
        testcase.assertTrue(turn["question"].strip())
        for page in turn.get("expected_pages", []):
            testcase.assertRegex(page, r"^(concepts|sources|entities|comparisons|workflows|queries)/.+\.md$")


class ChatEvalFixtureTests(unittest.TestCase):
    def test_main_agent_architecture_fixture_is_well_formed(self) -> None:
        data = _load_fixture(MAIN_FIXTURE_PATH)

        self.assertEqual(data["id"], "agent_architecture_6turn_mixed")
        self.assertEqual(data["recommended_scope"], "agent-engineering")
        self.assertIn("short-question noise control", data["evaluation_focus"])

        _assert_turns_well_formed(self, data, expected_count=6)

        self.assertEqual(data["turns"][0]["question"], "Agent Loop 是什么？")
        self.assertEqual(data["turns"][1]["question"], "和 Workflow 有什么区别？")

        final_turn = data["turns"][-1]
        self.assertEqual(final_turn["expected_pages"], [])
        self.assertGreaterEqual(len(final_turn["expected_behavior"]), 4)
        self.assertTrue(
            any("reuse prior conversation context" in item for item in final_turn["expected_behavior"])
        )

    def test_archived_agent_engineering_fixture_is_well_formed(self) -> None:
        data = _load_fixture(ARCHIVED_FIXTURE_PATH)

        self.assertEqual(data["id"], "agent_engineering_openclaw_9turn")
        self.assertEqual(data["recommended_scope"], "all_vaults")

        _assert_turns_well_formed(self, data, expected_count=9)

        final_turn = data["turns"][-1]
        self.assertEqual(final_turn["expected_pages"], [])
        self.assertGreaterEqual(len(final_turn["expected_behavior"]), 3)
        self.assertTrue(
            any("reuse prior conversation context" in item for item in final_turn["expected_behavior"])
        )

    def test_ios_audio_fixture_is_well_formed(self) -> None:
        data = _load_fixture(IOS_AUDIO_FIXTURE_PATH)

        self.assertEqual(data["id"], "ios_audio_tennis_detection_6turn")
        self.assertEqual(data["recommended_scope"], "ios-audio-project")
        self.assertIn("decision-oriented model selection", data["evaluation_focus"])
        self.assertGreaterEqual(len(data["rag_baseline"]["source_files"]), 3)

        _assert_turns_well_formed(self, data, expected_count=6)

        self.assertIn("iPhone", data["turns"][0]["question"])
        self.assertIn("SoundAnalysis", data["turns"][1]["question"])
        self.assertIn("MVP", data["turns"][-1]["question"])
        self.assertTrue(
            any("produce a roadmap" in item for item in data["turns"][-1]["expected_behavior"])
        )


if __name__ == "__main__":
    unittest.main()
