from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from knoarbor.entrypoints.api import create_app
from knoarbor.semantic.llm import ChatCompletionResponse, ProviderModelDiscovery


def _write_config(path: Path, *, api_key_env: str | None = None) -> None:
    payload = {
        "vault": {"path": str(path.parent / "wiki")},
        "models": {
            "default_provider": "local",
            "default_max_tokens": 30000,
            "request_timeout_seconds": 600,
            "providers": {
                "local": {
                    "base_url": "http://localhost:8001/v1",
                    "api_key_env": api_key_env,
                    "model": "qwen-local",
                    "json_mode": False,
                    "context_window": 16384,
                    "max_output_tokens": 4096,
                }
            },
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


class ModelProbeApiTests(unittest.TestCase):
    def test_providers_endpoint_hides_secrets_and_marks_local_provider_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            _write_config(config)
            client = TestClient(create_app())

            response = client.get("/models/providers", params={"config_path": str(config)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "model_providers.v1")
        self.assertEqual(payload["default_provider"], "local")
        provider = payload["providers"][0]
        self.assertEqual(provider["name"], "local")
        self.assertTrue(provider["api_key_configured"])
        self.assertTrue(provider["local_or_private"])
        self.assertNotIn("api_key", provider)

    def test_discover_endpoint_returns_detected_runtime_context_window(self) -> None:
        discovery = ProviderModelDiscovery(
            available=True,
            message="ok",
            details={
                "model_ids": ["qwen-local"],
                "model_count": 1,
                "configured_model_found": True,
                "detected_context_window": 32768,
                "context_window_source": "runtime",
            },
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            _write_config(config)
            client = TestClient(create_app())

            with patch("knoarbor.services.model_probe.ModelGateway.discover_models", return_value=discovery):
                response = client.post(
                    "/models/discover",
                    json={"config_path": str(config), "provider": "local"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "model_discovery.v1")
        self.assertTrue(payload["available"])
        self.assertEqual(payload["model_ids"], ["qwen-local"])
        self.assertEqual(payload["detected_context_window"], 32768)
        self.assertEqual(payload["effective_context_window"], 32768)
        self.assertEqual(payload["suggested_config"]["max_output_tokens"], 8000)

    def test_probe_endpoint_validates_structured_output(self) -> None:
        discovery = ProviderModelDiscovery(available=True, message="ok", details={"detected_context_window": 32768})
        completion = ChatCompletionResponse(
            content='{"ok": true, "value": 1}',
            provider="local",
            model="qwen-local",
            usage={"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
            elapsed_seconds=0.25,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            _write_config(config)
            client = TestClient(create_app())

            with (
                patch("knoarbor.services.model_probe.ModelGateway.discover_models", return_value=discovery),
                patch("knoarbor.services.model_probe.ModelGateway.complete", return_value=completion),
            ):
                response = client.post(
                    "/models/probe",
                    json={"config_path": str(config), "provider": "local", "level": "structured"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "model_probe.v1")
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["output_valid"])
        self.assertTrue(payload["structured_output"])
        self.assertEqual(payload["usage"]["total_tokens"], 17)

    def test_probe_endpoint_validates_minimal_output(self) -> None:
        discovery = ProviderModelDiscovery(available=True, message="ok", details={})
        completion = ChatCompletionResponse(content="OK", provider="local", model="qwen-local", elapsed_seconds=0.1)
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            _write_config(config)
            client = TestClient(create_app())

            with (
                patch("knoarbor.services.model_probe.ModelGateway.discover_models", return_value=discovery),
                patch("knoarbor.services.model_probe.ModelGateway.complete", return_value=completion),
            ):
                response = client.post(
                    "/models/probe",
                    json={"config_path": str(config), "provider": "local", "level": "minimal"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["output_valid"])
        self.assertIsNone(payload["structured_output"])

    def test_probe_requests_leave_budget_for_reasoning_models(self) -> None:
        captured = []
        discovery = ProviderModelDiscovery(available=True, message="ok", details={})

        def complete(request):
            captured.append(request)
            return ChatCompletionResponse(
                content='{"ok": true, "value": 1}' if len(captured) == 2 else "OK",
                provider="local",
                model="qwen-local",
                elapsed_seconds=0.1,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            _write_config(config)
            client = TestClient(create_app())

            with (
                patch("knoarbor.services.model_probe.ModelGateway.discover_models", return_value=discovery),
                patch("knoarbor.services.model_probe.ModelGateway.complete", side_effect=complete),
            ):
                minimal = client.post("/models/probe", json={"config_path": str(config), "provider": "local", "level": "minimal"})
                structured = client.post("/models/probe", json={"config_path": str(config), "provider": "local", "level": "structured"})

        self.assertEqual(minimal.status_code, 200)
        self.assertEqual(structured.status_code, 200)
        self.assertGreaterEqual(captured[0].max_tokens or 0, 64)
        self.assertGreaterEqual(captured[1].max_tokens or 0, 128)

    def test_probe_endpoint_reports_contract_warning_without_throwing(self) -> None:
        discovery = ProviderModelDiscovery(available=True, message="ok", details={})
        completion = ChatCompletionResponse(content="not json", provider="local", model="qwen-local", elapsed_seconds=0.1)
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            _write_config(config)
            client = TestClient(create_app())

            with (
                patch("knoarbor.services.model_probe.ModelGateway.discover_models", return_value=discovery),
                patch("knoarbor.services.model_probe.ModelGateway.complete", return_value=completion),
            ):
                response = client.post(
                    "/models/probe",
                    json={"config_path": str(config), "provider": "local", "level": "structured"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "warning")
        self.assertFalse(payload["output_valid"])
        self.assertFalse(payload["structured_output"])

    def test_apply_capabilities_explicitly_writes_selected_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            _write_config(config)
            client = TestClient(create_app())

            response = client.post(
                "/models/apply-capabilities",
                json={
                    "config_path": str(config),
                    "provider": "local",
                    "context_window": 32768,
                    "max_output_tokens": 8000,
                    "json_mode": True,
                },
            )
            data = yaml.safe_load(config.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "model_apply_capabilities.v1")
        self.assertTrue(payload["saved"])
        provider = data["models"]["providers"]["local"]
        self.assertEqual(provider["context_window"], 32768)
        self.assertEqual(provider["max_output_tokens"], 8000)
        self.assertTrue(provider["json_mode"])


if __name__ == "__main__":
    unittest.main()
