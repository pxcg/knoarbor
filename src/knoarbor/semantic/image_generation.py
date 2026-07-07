from __future__ import annotations

import base64
import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from knoarbor.core.config import ImageGenerationProviderConfig
from knoarbor.core.errors import ExternalServiceError, UserInputError
from knoarbor.core.schemas.image_generation import GeneratedImage, ImageGenerationRequest, ImageGenerationResponse


class ImageGenerationAdapter(Protocol):
    provider: str
    model: str

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        ...


@dataclass(frozen=True)
class ImageGenerationGateway:
    adapter: ImageGenerationAdapter

    @classmethod
    def from_config(
        cls,
        provider: str,
        config: ImageGenerationProviderConfig,
        *,
        timeout_seconds: float = 120.0,
    ) -> "ImageGenerationGateway":
        if config.adapter == "sensenova_image":
            return cls(SenseNovaImageClient.from_config(provider, config, timeout_seconds=timeout_seconds))
        raise UserInputError(f"Unsupported image generation adapter: {config.adapter}")

    @property
    def provider(self) -> str:
        return self.adapter.provider

    @property
    def model(self) -> str:
        return self.adapter.model

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        return self.adapter.generate(request)


@dataclass(frozen=True)
class SenseNovaImageClient:
    provider: str
    base_url: str
    endpoint_path: str
    api_key: str
    model: str
    timeout_seconds: float = 120.0
    verify_tls: bool = True
    tls_ca_file: str | None = None
    default_response_format: str = "url"
    default_resolution: str | None = "2720*1536"
    default_num_inference_steps: int | None = 20
    default_guidance: float | None = 4
    extra_body: dict[str, object] | None = None

    @classmethod
    def from_config(
        cls,
        provider: str,
        config: ImageGenerationProviderConfig,
        *,
        timeout_seconds: float = 120.0,
    ) -> "SenseNovaImageClient":
        base_url = (config.base_url or "").rstrip("/")
        model = config.model or ""
        api_key = config.resolved_api_key() or ""
        if not base_url:
            raise UserInputError(f"Image provider {provider} is missing base_url")
        if not model:
            raise UserInputError(f"Image provider {provider} is missing model")
        if not api_key:
            raise UserInputError(f"Image provider {provider} is missing API key")
        return cls(
            provider=provider,
            base_url=base_url,
            endpoint_path=config.endpoint_path,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            verify_tls=True,
            tls_ca_file=str(config.tls_ca_file) if config.tls_ca_file else None,
            default_response_format=config.response_format,
            default_resolution=config.resolution,
            default_num_inference_steps=config.num_inference_steps,
            default_guidance=config.guidance,
            extra_body=config.extra_body,
        )

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        started = time.perf_counter()
        payload = self._payload(request)
        raw = self._post_json(payload)
        images = _parse_images(raw)
        usage = _parse_usage(raw)
        usage["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return ImageGenerationResponse(
            provider=self.provider,
            model=self.model,
            prompt=request.prompt,
            images=images,
            usage=usage,
            raw=_compact_raw(raw),
        )

    def _payload(self, request: ImageGenerationRequest) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": request.prompt,
            "n": 1,
            "response_format": request.response_format or self.default_response_format,
        }
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt
        resolution = request.resolution or self.default_resolution
        if resolution:
            payload["resolution"] = resolution
        num_inference_steps = request.num_inference_steps or self.default_num_inference_steps
        if num_inference_steps is not None:
            payload["num_inference_steps"] = num_inference_steps
        guidance = request.guidance if request.guidance is not None else self.default_guidance
        if guidance is not None:
            payload["guidance"] = guidance
        payload.update(self.extra_body or {})
        payload.update(request.extra_body)
        return payload

    def _post_json(self, payload: dict[str, object]) -> dict[str, object]:
        url = self.base_url + (self.endpoint_path if self.endpoint_path.startswith("/") else f"/{self.endpoint_path}")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds, context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ExternalServiceError(f"Image provider {self.provider} returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(f"Image provider {self.provider} request failed: {exc.reason}") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ExternalServiceError(f"Image provider {self.provider} returned invalid JSON: {body[:300]}") from exc
        if not isinstance(parsed, dict):
            raise ExternalServiceError(f"Image provider {self.provider} returned a non-object response")
        return parsed


def _ssl_context(verify_tls: bool, tls_ca_file: str | None) -> ssl.SSLContext | None:
    if verify_tls and not tls_ca_file:
        return None
    if not verify_tls:
        return ssl._create_unverified_context()  # noqa: S323 - user-controlled local provider setting.
    return ssl.create_default_context(cafile=tls_ca_file)


def _parse_images(payload: dict[str, object]) -> list[GeneratedImage]:
    items = payload.get("data")
    if not isinstance(items, list):
        items = payload.get("images")
    if not isinstance(items, list):
        single = payload.get("image") or payload.get("url") or payload.get("b64_json")
        items = [single] if single else []
    images: list[GeneratedImage] = []
    for item in items:
        parsed = _parse_image_item(item)
        if parsed:
            images.append(parsed)
    return images


def _parse_image_item(item: object) -> GeneratedImage | None:
    if isinstance(item, str):
        if item.startswith("http://") or item.startswith("https://") or item.startswith("data:"):
            return GeneratedImage(url=item)
        if _looks_like_base64(item):
            return GeneratedImage(b64_json=item)
        return None
    if not isinstance(item, dict):
        return None
    url = _first_text(item, "url", "image_url", "image", "src")
    b64_json = _first_text(item, "b64_json", "base64", "image_base64")
    mime_type = _first_text(item, "mime_type", "mime") or "image/png"
    revised_prompt = _first_text(item, "revised_prompt", "prompt")
    if not url and b64_json and b64_json.startswith("data:"):
        url = b64_json
        b64_json = None
    return GeneratedImage(url=url, b64_json=b64_json, mime_type=mime_type, revised_prompt=revised_prompt) if url or b64_json else None


def _first_text(payload: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _looks_like_base64(value: str) -> bool:
    text = value.strip()
    if len(text) < 80:
        return False
    try:
        base64.b64decode(text[: min(len(text), 256)], validate=False)
    except Exception:
        return False
    return True


def _parse_usage(payload: dict[str, object]) -> dict[str, int]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    result: dict[str, int] = {}
    for key, value in usage.items():
        if isinstance(value, int):
            result[str(key)] = value
    return result


def _compact_raw(payload: dict[str, object]) -> dict[str, object]:
    compact = dict(payload)
    if "data" in compact:
        compact["data"] = "[image data omitted]"
    if "images" in compact:
        compact["images"] = "[image data omitted]"
    return compact
