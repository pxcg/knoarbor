from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from knoarbor.core.config import ImageGenerationProviderConfig
from knoarbor.core.schemas.image_generation import GeneratedImage, ImageGenerationRequest
from knoarbor.entrypoints.api import create_app
from knoarbor.semantic.image_generation import ImageGenerationGateway
from knoarbor.services.chat_generated_images import store_chat_generated_image


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
            api_key_env="SN_API_KEY",
            model="sensenova-u1-fast",
            resolution="2720*1536",
            num_inference_steps=20,
            guidance=4,
        )
        with patch.dict(os.environ, {"SN_API_KEY": "test-key"}), patch("knoarbor.semantic.image_generation.urllib.request.urlopen", fake_urlopen):
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
            api_key_env="SN_API_KEY",
            model="sensenova-u1-fast",
            response_format="b64_json",
        )
        with patch.dict(os.environ, {"SN_API_KEY": "test-key"}), patch("knoarbor.semantic.image_generation.urllib.request.urlopen", fake_urlopen):
            gateway = ImageGenerationGateway.from_config("sensenova", provider)
            response = gateway.generate(ImageGenerationRequest(prompt="A cover image"))

        self.assertEqual(response.images[0].b64_json, image_data)
        self.assertEqual(response.images[0].markdown_src(), f"data:image/jpeg;base64,{image_data}")

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
      api_key_env: SN_API_KEY
      model: sensenova-u1-fast
      resolution: "2720*1536"
      num_inference_steps: 20
      guidance: 4
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())
            with patch.dict(os.environ, {"SN_API_KEY": "test-key"}):
                response = client.get("/models/image-providers", params={"config_path": str(config)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "image_providers.v1")
        self.assertEqual(payload["default_provider"], "sensenova")
        self.assertEqual(payload["providers"][0]["name"], "sensenova")
        self.assertEqual(payload["providers"][0]["model"], "sensenova-u1-fast")
        self.assertEqual(payload["providers"][0]["resolution"], "2720*1536")
        self.assertTrue(payload["providers"][0]["api_key_configured"])

    def test_chat_generated_image_is_persisted_under_vault_assets(self) -> None:
        image_data = base64.b64encode(b"fake-png").decode("ascii")
        with tempfile.TemporaryDirectory() as tmp_dir:
            stored = store_chat_generated_image(
                GeneratedImage(b64_json=image_data, mime_type="image/png"),
                vault_path=tmp_dir,
                session_id="chat:demo",
                index=1,
            )

            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertTrue(stored.src.startswith("raw/assets/images/generated/chat/chat-demo/"))
            self.assertEqual((Path(tmp_dir) / stored.src).read_bytes(), b"fake-png")


if __name__ == "__main__":
    unittest.main()
