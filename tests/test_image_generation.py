from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from knoarbor.core.config import ImageGenerationProviderConfig
from knoarbor.core.schemas.image_generation import GeneratedImage, ImageGenerationRequest
from knoarbor.entrypoints.api import create_app
from knoarbor.semantic.image_generation import ImageGenerationGateway
from knoarbor.services.image_generation import ImageGenerationService
from knoarbor.services.chat_generated_images import delete_chat_request_artifacts, store_chat_generated_image


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ImageGenerationTests(unittest.TestCase):
    def test_image_generation_availability_requires_complete_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            complete = root / "complete.yaml"
            complete.write_text(
                """
vault:
  path: ./vault
image_generation:
  default_provider: sensenova
  providers:
    sensenova:
      adapter: sensenova_image
      base_url: https://token.sensenova.cn/v1
      api_key: test-key
      model: sensenova-u1-fast
""",
                encoding="utf-8",
            )
            incomplete = root / "incomplete.yaml"
            incomplete.write_text(
                """
vault:
  path: ./vault
image_generation:
  default_provider: sensenova
  providers:
    sensenova:
      adapter: sensenova_image
      base_url: https://token.sensenova.cn/v1
      model: sensenova-u1-fast
""",
                encoding="utf-8",
            )

            service = ImageGenerationService()
            self.assertTrue(service.is_available(str(complete)))
            self.assertFalse(service.is_available(str(incomplete)))

    def test_sensenova_image_client_parses_url_response(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, *, timeout=None, context=None):  # type: ignore[no-untyped-def]
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return _FakeHttpResponse({"data": [{"url": "https://example.com/generated.png"}], "usage": {"total_tokens": 12}})

        provider = ImageGenerationProviderConfig(
            base_url="https://token.sensenova.cn/v1",
            endpoint_path="/images/generations",
            api_key="test-key",
            model="sensenova-u1-fast",
            resolution="2720*1536",
            num_inference_steps=20,
            guidance=4,
        )
        with patch("knoarbor.semantic.image_generation.urllib.request.urlopen", fake_urlopen):
            gateway = ImageGenerationGateway.from_config("sensenova", provider, timeout_seconds=33)
            response = gateway.generate(ImageGenerationRequest(prompt="A clean product illustration"))

        self.assertEqual(response.provider, "sensenova")
        self.assertEqual(response.model, "sensenova-u1-fast")
        self.assertEqual(response.images[0].url, "https://example.com/generated.png")
        self.assertEqual(response.usage["total_tokens"], 12)
        self.assertEqual(captured["url"], "https://token.sensenova.cn/v1/images/generations")
        self.assertEqual(captured["body"]["model"], "sensenova-u1-fast")
        self.assertEqual(captured["body"]["prompt"], "A clean product illustration")
        self.assertEqual(captured["body"]["resolution"], "2720*1536")
        self.assertEqual(captured["body"]["num_inference_steps"], 20)
        self.assertEqual(captured["body"]["guidance"], 4)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(captured["timeout"], 33)

    def test_sensenova_image_client_parses_base64_response(self) -> None:
        image_data = "a" * 120

        def fake_urlopen(request, *, timeout=None, context=None):  # type: ignore[no-untyped-def]
            return _FakeHttpResponse({"images": [{"b64_json": image_data, "mime_type": "image/jpeg"}]})

        provider = ImageGenerationProviderConfig(
            base_url="https://token.sensenova.cn/v1",
            api_key="test-key",
            model="sensenova-u1-fast",
            response_format="b64_json",
        )
        with patch("knoarbor.semantic.image_generation.urllib.request.urlopen", fake_urlopen):
            gateway = ImageGenerationGateway.from_config("sensenova", provider)
            response = gateway.generate(ImageGenerationRequest(prompt="A cover image"))

        self.assertEqual(response.images[0].b64_json, image_data)
        self.assertEqual(response.images[0].markdown_src(), f"data:image/jpeg;base64,{image_data}")

    def test_openai_chat_image_client_uses_chat_completions_payload(self) -> None:
        image_data = "b" * 120
        captured: dict[str, object] = {}

        def fake_urlopen(request, *, timeout=None, context=None):  # type: ignore[no-untyped-def]
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            captured["context"] = context
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                                    }
                                ]
                            }
                        }
                    ],
                    "usage": {"total_tokens": 8},
                }
            )

        provider = ImageGenerationProviderConfig(
            adapter="openai_chat_image",
            base_url="https://text2image.local/v1",
            endpoint_path="/chat/completions",
            api_key="test-key",
            model="SenseNova-U1-8B",
            num_inference_steps=20,
            guidance=4,
            extra_body={"seed": 42},
        )
        with patch("knoarbor.semantic.image_generation.urllib.request.urlopen", fake_urlopen):
            gateway = ImageGenerationGateway.from_config("local-chat-image", provider, timeout_seconds=44)
            response = gateway.generate(ImageGenerationRequest(prompt="A local image"))

        body = captured["body"]
        self.assertIsInstance(body, dict)
        assert isinstance(body, dict)
        self.assertEqual(captured["url"], "https://text2image.local/v1/chat/completions")
        self.assertEqual(body["model"], "SenseNova-U1-8B")
        self.assertEqual(body["messages"], [{"role": "user", "content": "A local image"}])
        self.assertEqual(body["extra_body"]["modalities"], ["image"])  # type: ignore[index]
        self.assertEqual(body["extra_body"]["num_inference_steps"], 20)  # type: ignore[index]
        self.assertEqual(body["extra_body"]["guidance_scale"], 4)  # type: ignore[index]
        self.assertEqual(body["extra_body"]["seed"], 42)  # type: ignore[index]
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-key")  # type: ignore[index]
        self.assertEqual(captured["timeout"], 44)
        self.assertEqual(response.provider, "local-chat-image")
        self.assertEqual(response.images[0].url, f"data:image/png;base64,{image_data}")
        self.assertEqual(response.usage["total_tokens"], 8)
        self.assertEqual(response.raw["choices"], "[chat image data omitted]")

    def test_openai_chat_image_client_parses_plain_base64_content(self) -> None:
        image_data = "c" * 120

        def fake_urlopen(request, *, timeout=None, context=None):  # type: ignore[no-untyped-def]
            return _FakeHttpResponse({"choices": [{"message": {"content": image_data}}]})

        provider = ImageGenerationProviderConfig(
            adapter="openai_chat_image",
            base_url="https://text2image.local/v1",
            api_key="test-key",
            model="SenseNova-U1-8B",
        )
        with patch("knoarbor.semantic.image_generation.urllib.request.urlopen", fake_urlopen):
            gateway = ImageGenerationGateway.from_config("local-chat-image", provider)
            response = gateway.generate(ImageGenerationRequest(prompt="A local image"))

        self.assertEqual(response.images[0].b64_json, image_data)

    def test_image_providers_api_lists_configured_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = root / "config.yaml"
            config.write_text(
                """
vault:
  path: ./vaults/default
image_generation:
  default_provider: sensenova
  providers:
    sensenova:
      adapter: sensenova_image
      base_url: https://token.sensenova.cn/v1
      endpoint_path: /images/generations
      api_key: test-key
      model: sensenova-u1-fast
      resolution: "2720*1536"
      num_inference_steps: 20
      guidance: 4
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())
            response = client.get("/models/image-providers", params={"config_path": str(config)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "image_providers.v1")
        self.assertEqual(payload["default_provider"], "sensenova")
        self.assertEqual(payload["providers"][0]["name"], "sensenova")
        self.assertEqual(payload["providers"][0]["model"], "sensenova-u1-fast")
        self.assertEqual(payload["providers"][0]["resolution"], "2720*1536")
        self.assertNotIn("api_key", payload["providers"][0])

    def test_image_providers_api_lists_openai_chat_image_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = root / "config.yaml"
            config.write_text(
                """
vault:
  path: ./vaults/default
image_generation:
  default_provider: local-chat-image
  providers:
    local-chat-image:
      adapter: openai_chat_image
      base_url: https://text2image.local/v1
      endpoint_path: /chat/completions
      api_key: test-key
      model: SenseNova-U1-8B
      tls_ca_file: ./company-ca.pem
      num_inference_steps: 20
      guidance: 4
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())
            response = client.get("/models/image-providers", params={"config_path": str(config)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default_provider"], "local-chat-image")
        self.assertEqual(payload["providers"][0]["adapter"], "openai_chat_image")
        self.assertEqual(payload["providers"][0]["model"], "SenseNova-U1-8B")

    def test_image_provider_probe_runs_explicit_generation_without_returning_image_data(self) -> None:
        image_data = "d" * 120
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            config.write_text(
                """
vault:
  path: ./vaults/default
image_generation:
  default_provider: local-chat-image
  providers:
    local-chat-image:
      adapter: openai_chat_image
      base_url: https://text2image.local/v1
      endpoint_path: /chat/completions
      api_key: test-key
      model: SenseNova-U1-8B
""",
                encoding="utf-8",
            )

            def fake_urlopen(request, *, timeout=None, context=None):  # type: ignore[no-untyped-def]
                return _FakeHttpResponse(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": [
                                        {
                                            "type": "image_url",
                                            "image_url": {"url": f"data:image/png;base64,{image_data}"},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                )

            client = TestClient(create_app())
            with patch("knoarbor.semantic.image_generation.urllib.request.urlopen", fake_urlopen):
                response = client.post(
                    "/models/image-probe",
                    json={"config_path": str(config), "provider": "local-chat-image"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "image_provider_probe.v1")
        self.assertTrue(payload["available"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["image_count"], 1)
        self.assertEqual(payload["mime_types"], ["image/png"])
        self.assertNotIn(image_data, response.text)

    def test_image_provider_probe_reports_empty_generation_as_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            config.write_text(
                """
vault:
  path: ./vaults/default
image_generation:
  default_provider: sensenova
  providers:
    sensenova:
      adapter: sensenova_image
      base_url: https://token.sensenova.cn/v1
      api_key: test-key
      model: sensenova-u1-fast
""",
                encoding="utf-8",
            )

            client = TestClient(create_app())
            with patch(
                "knoarbor.semantic.image_generation.urllib.request.urlopen",
                return_value=_FakeHttpResponse({"data": []}),
            ):
                response = client.post(
                    "/models/image-probe",
                    json={"config_path": str(config), "provider": "sensenova"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["available"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["image_count"], 0)
        self.assertEqual(payload["error_code"], "KA-INPUT-001")


    def test_chat_generated_image_is_persisted_under_vault_assets(self) -> None:
        image_data = base64.b64encode(b"fake-png").decode("ascii")
        with tempfile.TemporaryDirectory() as tmp_dir:
            stored = store_chat_generated_image(
                GeneratedImage(b64_json=image_data, mime_type="image/png"),
                vault_path=tmp_dir,
                session_id="chat:demo",
                request_id="req_demo",
                index=1,
            )

            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertTrue(stored.src.startswith("artifacts/chat/chat_demo/images/"))
            self.assertEqual((Path(tmp_dir) / stored.src).read_bytes(), b"fake-png")
            self.assertIsNotNone(stored.manifest_path)
            assert stored.manifest_path is not None
            manifest = json.loads(Path(stored.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "knoarbor.chat_artifacts.v1")
            self.assertEqual(manifest["session_id"], "chat:demo")
            self.assertEqual(manifest["images"][0]["src"], stored.src)
            self.assertEqual(manifest["images"][0]["request_id"], "req_demo")
            self.assertNotIn("original_src", manifest["images"][0])
            self.assertEqual(manifest["images"][0]["mime_type"], "image/png")
            self.assertEqual(manifest["images"][0]["size_bytes"], len(b"fake-png"))

            Path(stored.manifest_path).unlink()
            delete_chat_request_artifacts(tmp_dir, "chat:demo", "req_demo")
            self.assertFalse(Path(stored.path).exists())


if __name__ == "__main__":
    unittest.main()
