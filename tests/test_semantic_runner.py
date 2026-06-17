from __future__ import annotations

import sys
import http.client
import json
import ssl
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import ModelProviderConfig
from knoarbor.core.errors import ExternalServiceError
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.semantic import (
    ChatCompletionRequest,
    ModelGateway,
    OllamaNativeChatClient,
    OpenAICompatibleChatClient,
    SemanticRetryPolicy,
    SemanticRunner,
    build_semantic_prompt_package,
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
        self.assertIn("semantic contract executor", client.last_request.messages[0].content)
        self.assertIn("Contract instructions:", client.last_request.messages[1].content)
        self.assertIn("Stable contract execution preamble", client.last_request.messages[1].content)
        self.assertIn("source_document", client.last_request.messages[2].content)
        self.assertGreater(result.metrics["prompt_stable_chars"], 0)
        self.assertGreater(result.metrics["prompt_dynamic_chars"], 0)
        self.assertEqual(result.metrics["prompt_stable_message_count"], 2)
        self.assertEqual(result.metrics["prompt_dynamic_message_count"], 1)
        self.assertEqual(result.metrics["payload_top_field"], "source_document")
        self.assertGreater(result.metrics["payload_char_total"], 0)
        self.assertIn("source_document", result.metrics["payload_char_breakdown"])

    def test_semantic_prompt_package_keeps_payload_out_of_stable_prefix(self) -> None:
        contract = load_semantic_contract("source_normalize")

        first = build_semantic_prompt_package(contract, {"source_document": {"title": "First Payload"}})
        second = build_semantic_prompt_package(contract, {"source_document": {"title": "Second Payload"}})

        self.assertEqual(first.messages[0].content, second.messages[0].content)
        self.assertEqual(first.messages[1].content, second.messages[1].content)
        self.assertEqual(first.stable_chars, second.stable_chars)
        self.assertNotEqual(first.messages[2].content, second.messages[2].content)
        self.assertNotIn("First Payload", first.messages[0].content)
        self.assertNotIn("First Payload", first.messages[1].content)
        self.assertIn("First Payload", first.messages[2].content)

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

    def test_model_gateway_wraps_openai_compatible_adapter(self) -> None:
        gateway = ModelGateway.from_config(
            "local",
            ModelProviderConfig(base_url="http://127.0.0.1:11434/v1", model="qwen"),
            timeout_seconds=300,
        )

        self.assertEqual(gateway.provider, "local")
        self.assertEqual(gateway.model, "qwen")
        self.assertEqual(gateway.adapter.timeout_seconds, 300)

    def test_model_gateway_wraps_ollama_native_adapter(self) -> None:
        gateway = ModelGateway.from_config(
            "ollama",
            ModelProviderConfig(adapter="ollama", base_url="http://127.0.0.1:11434", model="qwen"),
            timeout_seconds=300,
        )

        self.assertEqual(gateway.provider, "ollama")
        self.assertEqual(gateway.model, "qwen")
        self.assertIsInstance(gateway.adapter, OllamaNativeChatClient)
        self.assertEqual(gateway.adapter.timeout_seconds, 300)

    def test_openai_compatible_client_allows_local_no_auth(self) -> None:
        client = OpenAICompatibleChatClient.from_config(
            "local",
            ModelProviderConfig(base_url="http://127.0.0.1:11434/v1", model="qwen"),
        )

        captured_auth: str | None = "unset"

        def fake_urlopen(request, **_kwargs):
            nonlocal captured_auth
            captured_auth = request.get_header("Authorization")
            return FakeHTTPResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}]))

        self.assertIsNone(captured_auth)

    def test_ollama_native_client_uses_api_chat_without_thinking_by_default(self) -> None:
        client = OllamaNativeChatClient.from_config(
            "ollama",
            ModelProviderConfig(adapter="ollama", base_url="http://127.0.0.1:11434", model="qwen", json_mode=True),
        )

        captured_payload: dict[str, object] = {}
        captured_url = ""

        class OllamaChatResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "message": {"role": "assistant", "content": '{"ok": true}'},
                        "prompt_eval_count": 10,
                        "eval_count": 4,
                        "eval_duration": 2_000_000_000,
                    }
                ).encode("utf-8")

        def fake_urlopen(request, **_kwargs):
            nonlocal captured_payload, captured_url
            captured_url = request.full_url
            captured_payload = json.loads(request.data.decode("utf-8"))
            return OllamaChatResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            response = client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}], max_tokens=64))

        self.assertEqual(captured_url, "http://127.0.0.1:11434/api/chat")
        self.assertFalse(captured_payload["think"])
        self.assertFalse(captured_payload["stream"])
        self.assertEqual(captured_payload["format"], "json")
        self.assertEqual(captured_payload["options"], {"temperature": 0.1, "num_predict": 64})
        self.assertEqual(response.content, '{"ok": true}')
        self.assertEqual(response.usage["total_tokens"], 14)
        self.assertEqual(response.tokens_per_second, 2.0)

    def test_ollama_native_client_merges_multiple_system_messages(self) -> None:
        client = OllamaNativeChatClient.from_config(
            "ollama",
            ModelProviderConfig(adapter="ollama", base_url="http://127.0.0.1:11434", model="qwen", json_mode=False),
        )

        captured_payload: dict[str, object] = {}

        class OllamaChatResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"message":{"role":"assistant","content":"ok"},"prompt_eval_count":1,"eval_count":1}'

        def fake_urlopen(request, **_kwargs):
            nonlocal captured_payload
            captured_payload = json.loads(request.data.decode("utf-8"))
            return OllamaChatResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.complete(
                ChatCompletionRequest(
                    messages=[
                        {"role": "system", "content": "Stable prompt."},
                        {"role": "system", "content": "Memory context."},
                        {"role": "user", "content": "hello"},
                    ],
                    structured_output=False,
                )
            )

        messages = captured_payload["messages"]
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("Stable prompt.", messages[0]["content"])
        self.assertIn("Memory context.", messages[0]["content"])

    def test_ollama_native_client_discovers_models_and_context_window(self) -> None:
        client = OllamaNativeChatClient(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="qwen3:14b",
            configured_context_window=32768,
        )

        class TagsResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"models":[{"name":"qwen3:14b"},{"name":"llama3.1:8b"}]}'

        class ShowResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"model_info":{"qwen3.context_length":65536}}'

        def fake_urlopen(request, **_kwargs):
            if request.full_url.endswith("/api/show"):
                return ShowResponse()
            return TagsResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            discovery = client.discover_models()

        self.assertTrue(discovery.available)
        self.assertTrue(discovery.details["models_list_valid"])
        self.assertEqual(discovery.details["model_count"], 2)
        self.assertTrue(discovery.details["configured_model_found"])
        self.assertEqual(discovery.details["detected_context_window"], 65536)
        self.assertEqual(discovery.details["effective_context_window"], 65536)

    def test_openai_compatible_client_requests_json_mode_by_default(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="deepseek",
            base_url="https://api.example.test",
            api_key="test-key",
            model="deepseek-chat",
        )

        captured_payload: dict[str, object] = {}

        def fake_urlopen(request, **_kwargs):
            nonlocal captured_payload
            captured_payload = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}]))

        self.assertEqual(captured_payload["response_format"], {"type": "json_object"})

    def test_openai_compatible_client_merges_multiple_system_messages(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="vllm",
            base_url="http://127.0.0.1:8001/v1",
            api_key="test-key",
            model="qwen",
            json_mode=False,
        )

        captured_payload: dict[str, object] = {}

        def fake_urlopen(request, **_kwargs):
            nonlocal captured_payload
            captured_payload = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.complete(
                ChatCompletionRequest(
                    messages=[
                        {"role": "system", "content": "Stable prompt."},
                        {"role": "system", "content": "Workspace context."},
                        {"role": "user", "content": "hello"},
                    ],
                    structured_output=False,
                )
            )

        messages = captured_payload["messages"]
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("Stable prompt.", messages[0]["content"])
        self.assertIn("Workspace context.", messages[0]["content"])

    def test_openai_compatible_client_extracts_provider_cache_telemetry(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="openai",
            base_url="https://api.example.test",
            api_key="test-key",
            model="gpt-test",
        )

        captured_payload: dict[str, object] = {}

        def fake_urlopen(request, **_kwargs):
            nonlocal captured_payload
            captured_payload = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            response = client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}]))

        self.assertNotIn("prompt_cache_key", captured_payload)
        self.assertEqual(response.usage["prompt_cache_hit_tokens"], 64)
        self.assertEqual(response.usage["prompt_cache_miss_tokens"], 36)
        self.assertEqual(response.usage["prompt_cached_tokens"], 48)

    def test_openai_compatible_client_reports_models_list_details(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="ollama",
            base_url="http://127.0.0.1:11434/v1",
            api_key="",
            model="qwen3:14b",
            json_mode=False,
            configured_context_window=32768,
        )

        class ModelsResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"object":"list","data":[{"id":"qwen3:14b","max_model_len":65536},{"id":"llama3.1:8b"}]}'

        with patch("urllib.request.urlopen", return_value=ModelsResponse()):
            health = client.check()

        self.assertTrue(health.available)
        self.assertTrue(health.details["models_list_valid"])
        self.assertEqual(health.details["model_count"], 2)
        self.assertTrue(health.details["configured_model_found"])
        self.assertEqual(health.details["detected_context_window"], 65536)
        self.assertEqual(health.details["effective_context_window"], 65536)
        self.assertEqual(health.details["context_window_source"], "runtime")

    def test_openai_compatible_client_detects_ollama_context_window_from_show(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="ollama",
            base_url="http://127.0.0.1:11434/v1",
            api_key="",
            model="qwen3:14b",
            json_mode=False,
            configured_context_window=32768,
        )

        class ModelsResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"object":"list","data":[{"id":"qwen3:14b"}]}'

        class ShowResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"model_info":{"qwen3.context_length":40960},"parameters":"temperature 0.7\\nnum_ctx 32768"}'

        def fake_urlopen(request, **_kwargs):
            if request.full_url.endswith("/api/show"):
                return ShowResponse()
            return ModelsResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            health = client.check()

        self.assertTrue(health.available)
        self.assertTrue(health.details["ollama_show_available"])
        self.assertEqual(health.details["detected_context_window"], 40960)
        self.assertEqual(health.details["effective_context_window"], 40960)
        self.assertEqual(health.details["context_window_source"], "runtime")

    def test_openai_compatible_client_falls_back_to_configured_context_window(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="vllm",
            base_url="http://127.0.0.1:8001/v1",
            api_key="",
            model="local-model",
            json_mode=True,
            configured_context_window=32768,
        )

        class ModelsResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"object":"list","data":[{"id":"local-model"}]}'

        with patch("urllib.request.urlopen", return_value=ModelsResponse()):
            health = client.check()

        self.assertTrue(health.available)
        self.assertIsNone(health.details["detected_context_window"])
        self.assertEqual(health.details["effective_context_window"], 32768)
        self.assertEqual(health.details["context_window_source"], "config")

    def test_openai_compatible_client_reports_empty_ollama_model_list(self) -> None:
        client = OpenAICompatibleChatClient(
            provider="ollama",
            base_url="http://127.0.0.1:11434/v1",
            api_key="",
            model="qwen3:14b",
            json_mode=False,
        )

        class ModelsResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"object":"list","data":null}'

        with patch("urllib.request.urlopen", return_value=ModelsResponse()):
            health = client.check()

        self.assertTrue(health.available)
        self.assertFalse(health.details["models_list_valid"])
        self.assertFalse(health.details["configured_model_found"])

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

        with patch("urllib.request.urlopen", side_effect=ssl.SSLError("tls alert")):
            with self.assertRaisesRegex(ExternalServiceError, "response was interrupted"):
                client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}]))

        with patch("urllib.request.urlopen", side_effect=http.client.RemoteDisconnected("closed")):
            with self.assertRaisesRegex(ExternalServiceError, "response was interrupted"):
                client.complete(ChatCompletionRequest(messages=[{"role": "user", "content": "hello"}]))


if __name__ == "__main__":
    unittest.main()
