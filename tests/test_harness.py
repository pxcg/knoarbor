from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.semantic import ChatCompletionRequest, SemanticRunner

from tests.harness.llm import ScriptedChatClient
from tests.harness.semantic_cases import lint_candidates_output, markdown_source_document
from tests.harness.snapshot import canonical_json


class HarnessTests(unittest.TestCase):
    def test_scripted_chat_client_records_requests_and_outputs_json(self) -> None:
        client = ScriptedChatClient.single(lint_candidates_output())

        result = SemanticRunner(client).run("lint_diagnose", {"scan": {"title": "Harness Unit"}})

        self.assertEqual(client.calls, 1)
        self.assertEqual(result.output.summary, "One candidate.")
        self.assertIsInstance(client.last_request, ChatCompletionRequest)

    def test_markdown_source_document_fixture_is_stable(self) -> None:
        document = markdown_source_document(title="Harness Agent", text="# Harness Agent\n\nLoop notes.")

        self.assertEqual(document.source_type, "markdown")
        self.assertEqual(document.metadata["title"], "Harness Agent")
        self.assertEqual(document.content.text, "# Harness Agent\n\nLoop notes.")

    def test_canonical_json_sorts_keys_for_snapshots(self) -> None:
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{\n  "a": 1,\n  "b": 2\n}\n')


if __name__ == "__main__":
    unittest.main()
