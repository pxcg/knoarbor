from __future__ import annotations

import sys
import http.client
import json
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import ModelProviderConfig
from knoarbor.core.errors import ExternalServiceError
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.semantic import (
    ChatCompletionRequest,
    OpenAICompatibleChatClient,
    SemanticRetryPolicy,
    SemanticRunner,
    load_semantic_contract,
    parse_contract_output,
)
from tests.harness.llm import ScriptedChatClient


class FakeHTTPResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "prompt_cache_hit_tokens": 64,
                    "prompt_cache_miss_tokens": 36,
                    "prompt_tokens_details": {"cached_tokens": 48},
                },
                "choices": [
                    {
                        "message": {
                            "content": '{"output":{"schema_version":"knowledge_extract.v1"}}',
                        }
                    }
                ]
            }
        ).encode("utf-8")


class SemanticRunnerTests(unittest.TestCase):
    def test_parse_contract_output_requires_top_level_output(self) -> None:
        contract = load_semantic_contract("source_normalize")

        parsed = parse_contract_output(
            contract,
            """
            {
              "output": {
                "schema_version": "knowledge_extract.v1",
                "source": {
                  "source_type": "markdown",
                  "source_app": "unit",
                  "source_id": "unit:1",
                  "source_path": "raw/notes/unit.md",
                  "title": "Unit",
                  "created_at": null,
                  "updated_at": null
                },
                "content_units": [
                  {
                    "index": 0,
                    "unit_type": "note",
                    "role": "note",
                    "title": "Unit",
                    "content": "Unit note.",
                    "timestamp": null,
                    "is_primary": true,
                    "metadata": {}
                  }
                ],
                "compile_context": {
                  "primary_content": "Unit note.",
                  "supporting_evidence": [],
                  "links": [],
                  "latest_unit_indexes": [0]
                },
                "confidence": 0.9,
                "warnings": []
              }
            }
            """,
        )

        self.assertIsInstance(parsed, KnowledgeExtract)
        self.assertEqual(parsed.source.title, "Unit")

    def test_parse_contract_output_accepts_schema_root_payload(self) -> None:
        contract = load_semantic_contract("source_normalize")

        parsed = parse_contract_output(
            contract,
            """
            {
              "schema_version": "knowledge_extract.v1",
              "source": {
                "source_type": "markdown",
                "source_app": "unit",
                "source_id": "unit:1",
                "source_path": "raw/notes/unit.md",
                "title": "Schema Root",
                "created_at": null,
                "updated_at": null
              },
              "content_units": [
                {
                  "index": 0,
                  "unit_type": "note",
                  "role": "note",
                  "title": "Schema Root",
                  "content": "Schema root note.",
                  "timestamp": null,
                  "is_primary": true,
                  "metadata": {}
                }
              ],
              "compile_context": {
                "primary_content": "Schema root note.",
                "supporting_evidence": [],
                "links": [],
                "latest_unit_indexes": [0]
              },
              "confidence": 0.9,
              "warnings": []
            }
            """,
        )

        self.assertIsInstance(parsed, KnowledgeExtract)
        self.assertEqual(parsed.source.title, "Schema Root")

    def test_parse_contract_output_rejects_unrelated_json_object(self) -> None:
        contract = load_semantic_contract("source_normalize")

        with self.assertRaises(ValueError):
            parse_contract_output(contract, '{"schema_version": "unknown.v1"}')

    def test_semantic_runner_builds_prompt_and_validates_output(self) -> None:
        content = """
        {
          "output": {
            "schema_version": "knowledge_extract.v1",
            "source": {
              "source_type": "markdown",
              "source_app": "unit",
              "source_id": "unit:2",
              "source_path": "raw/notes/unit.md",
              "title": "Runner Unit",
              "created_at": null,
              "updated_at": null
            },
            "content_units": [
              {
                "index": 0,
                "unit_type": "note",
                "role": "note",
                "title": "Runner Unit",
                "content": "Runner note.",
                "timestamp": null,
                "is_primary": true,
                "metadata": {}
              }
            ],
            "compile_context": {
              "primary_content": "Runner note.",
              "supporting_evidence": [],
              "links": [],
              "latest_unit_indexes": [0]
            },
            "confidence": 0.9,
            "warnings": []
          }
        }
        """
        client = ScriptedChatClient.single(content)
        result = SemanticRunner(client).run("source_normalize", {"source_document": {"title": "Runner Unit"}})

        self.assertEqual(result.provider, "fake")
        self.assertEqual(result.schema_version, "knowledge_extract.v1")
        self.assertIsNotNone(client.last_request)
        assert client.last_request is not None
        self.assertEqual(client.last_request.messages[0].role, "system")
        self.assertIn("Stable contract execution preamble", client.last_request.messages[1].content)
        self.assertIn("source_document", client.last_request.messages[2].content)

    def test_semantic_runner_retries_retryable_provider_failure(self) -> None:
        valid = """
        {
          "output": {
            "schema_version": "knowledge_extract.v1",
            "source": {
              "source_type": "markdown",
              "source_app": "unit",
              "source_id": "unit:retry",
              "source_path": "raw/notes/unit.md",
              "title": "Retry Unit",
              "created_at": null,
              "updated_at": null
            },
            "content_units": [
              {
                "index": 0,
                "unit_type": "note",
                "role": "note",
                "title": "Retry Unit",
                "content": "Retry note.",
                "timestamp": null,
                "is_primary": true,
                "metadata": {}
              }
            ],
            "compile_context": {
              "primary_content": "Retry note.",
              "supporting_evidence": [],
              "links": [],
              "latest_unit_indexes": [0]
            },
            "confidence": 0.9,
            "warnings": []
          }
        }
        """
        client = ScriptedChatClient([ExternalServiceError("temporary provider failure"), valid])
        runner = SemanticRunner(client, retry_policy=SemanticRetryPolicy(max_attempts=2, backoff_seconds=0))

        result = runner.run("source_normalize", {"source_document": {"title": "Retry Unit"}})

        self.assertEqual(client.calls, 2)
        self.assertEqual(result.output.source.title, "Retry Unit")
        self.assertEqual(len(runner.history), 2)
        self.assertEqual(runner.history[0].metrics.get("error_type"), "ExternalServiceError")
        self.assertEqual(runner.history[0].metrics.get("error_code"), "KA-EXT-001")
        self.assertEqual(runner.history[0].metrics.get("error_retryable"), True)

    def test_semantic_runner_respects_retryable_error_code_allowlist(self) -> None:
        client = ScriptedChatClient([ExternalServiceError("temporary provider failure")])
        runner = SemanticRunner(
            client,
            retry_policy=SemanticRetryPolicy(
                max_attempts=2,
                backoff_seconds=0,
                retryable_error_codes=frozenset({"KA-STORAGE-001"}),
            ),
        )

        with self.assertRaises(ExternalServiceError):
            runner.run("source_normalize", {"source_document": {"title": "Retry Unit"}})

        self.assertEqual(client.calls, 1)

    def test_semantic_runner_retries_invalid_structured_output(self) -> None:
        valid = """
        {
          "output": {
            "schema_version": "knowledge_extract.v1",
            "source": {
              "source_type": "markdown",
              "source_app": "unit",
              "source_id": "unit:json-retry",
              "source_path": "raw/notes/unit.md",
              "title": "JSON Retry Unit",
              "created_at": null,
              "updated_at": null
            },
            "content_units": [
              {
                "index": 0,
                "unit_type": "note",
                "role": "note",
                "title": "JSON Retry Unit",
                "content": "JSON retry note.",
                "timestamp": null,
                "is_primary": true,
                "metadata": {}
              }
            ],
            "compile_context": {
              "primary_content": "JSON retry note.",
              "supporting_evidence": [],
              "links": [],
              "latest_unit_indexes": [0]
            },
            "confidence": 0.9,
            "warnings": []
          }
        }
        """
        client = ScriptedChatClient(["not-json", valid])
        runner = SemanticRunner(client, retry_policy=SemanticRetryPolicy(max_attempts=2, backoff_seconds=0))

        result = runner.run("source_normalize", {"source_document": {"title": "JSON Retry Unit"}})

        self.assertEqual(client.calls, 2)
        self.assertEqual(result.output.source.title, "JSON Retry Unit")
        self.assertEqual(runner.history[0].metrics.get("error_type"), "ModelOutputError")
        self.assertEqual(runner.history[0].metrics.get("error_code"), "KA-MODEL-001")

    def test_openai_compatible_client_requires_complete_provider_config(self) -> None:
        with self.assertRaises(ValueError):
            OpenAICompatibleChatClient.from_config("deepseek", ModelProviderConfig(model="deepseek-chat"))

    def test_openai_compatible_client_uses_configured_timeout(self) -> None:
        with patch.dict("os.environ", {"TEST_MODEL_KEY": "test-key"}):
            client = OpenAICompatibleChatClient.from_config(
                "deepseek",
                ModelProviderConfig(
                    base_url="https://api.example.test",
                    api_key_env="TEST_MODEL_KEY",
                    model="deepseek-chat",
                ),
                timeout_seconds=300,
            )

        self.assertEqual(client.timeout_seconds, 300)

    def test_openai_compatible_client_requests_json_mode_by_default(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="deepseek",
            base_url="https://api.example.test",
            api_key="test-key",
            model="deepseek-chat",
        )

        captured_payload: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            nonlocal captured_payload
            captured_payload = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}]))

        self.assertEqual(captured_payload["response_format"], {"type": "json_object"})

    def test_openai_compatible_client_extracts_provider_cache_telemetry(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="openai",
            base_url="https://api.example.test",
            api_key="test-key",
            model="gpt-test",
        )

        captured_payload: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            nonlocal captured_payload
            captured_payload = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            response = client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}]))

        self.assertNotIn("prompt_cache_key", captured_payload)
        self.assertEqual(response.usage["prompt_cache_hit_tokens"], 64)
        self.assertEqual(response.usage["prompt_cache_miss_tokens"], 36)
        self.assertEqual(response.usage["prompt_cached_tokens"], 48)

    def test_openai_compatible_client_wraps_interrupted_responses(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="deepseek",
            base_url="https://api.example.test",
            api_key="test-key",
            model="deepseek-chat",
        )

        with patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"")):
            with self.assertRaisesRegex(ExternalServiceError, "response was interrupted"):
                client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}]))


if __name__ == "__main__":
    unittest.main()
