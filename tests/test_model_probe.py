from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from knoarbor.entrypoints.api import create_app
from knoarbor.semantic.llm import ProviderModelDiscovery


def _write_config(path: Path, *, api_key: str | None = None, model: str = "qwen-local") -> None:
    payload = {
        "vault": {"path": str(path.parent / "wiki")},
        "models": {
            "default_provider": "local",
            "default_max_tokens": 30000,
            "request_timeout_seconds": 600,
            "providers": {
                "local": {
                    "base_url": "http://localhost:8001/v1",
                    "api_key": api_key,
                    "model": model,
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

    def test_discover_endpoint_does_not_require_selected_model(self) -> None:
        discovery = ProviderModelDiscovery(
            available=True,
            message="ok",
            details={
                "model_ids": ["qwen3:14b", "qwen3.6:27b-q4_K_M"],
                "model_count": 2,
                "configured_model_found": False,
            },
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            _write_config(config, model="")
            client = TestClient(create_app())

            with patch("knoarbor.services.model_probe.ModelGateway.discover_models", return_value=discovery):
                response = client.post(
                    "/models/discover",
                    json={"config_path": str(config), "provider": "local"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["available"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["model"], "")
        self.assertEqual(payload["model_ids"], ["qwen3:14b", "qwen3.6:27b-q4_K_M"])

    def test_discover_endpoint_warns_when_configured_model_is_missing(self) -> None:
        discovery = ProviderModelDiscovery(
            available=True,
            message="ok",
            details={"model_ids": ["other-model"], "model_count": 1, "configured_model_found": False},
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
        self.assertEqual(payload["status"], "warning")
        self.assertTrue(payload["available"])
        self.assertIn("Configured model was not found", payload["message"])

    def test_discover_endpoint_reports_api_connectivity_failure(self) -> None:
        discovery = ProviderModelDiscovery(available=False, message="Provider endpoint request failed: refused", details={})
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
        self.assertEqual(payload["status"], "error")
        self.assertFalse(payload["available"])
        self.assertIn("Provider endpoint request failed", payload["message"])

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
