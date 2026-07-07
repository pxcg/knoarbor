from __future__ import annotations

import json
import http.client
import ipaddress
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from collections.abc import Iterator
from typing import Protocol

import certifi
from pydantic import BaseModel, Field

from knoarbor.core.config import ModelProviderConfig
from knoarbor.core.errors import ExternalServiceError, ModelOutputError, SemanticContractError, UserInputError


class ChatMessage(BaseModel):
    role: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    structured_output: bool = True


class ChatCompletionResponse(BaseModel):
    content: str
    provider: str
    model: str
    raw: dict[str, object] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    elapsed_seconds: float = 0.0
    tokens_per_second: float | None = None


class ChatCompletionStreamChunk(BaseModel):
    delta: str = ""
    response: ChatCompletionResponse | None = None


class ChatClient(Protocol):
    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        ...


class ProviderHealthCheck(BaseModel):
    available: bool
    structured_output: bool | None = None
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ProviderModelDiscovery(BaseModel):
    available: bool
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ProviderAdapter(ChatClient, Protocol):
    provider: str
    model: str

    def check(self) -> ProviderHealthCheck:
        ...

    def discover_models(self) -> ProviderModelDiscovery:
        ...


@dataclass(frozen=True)
class ModelGateway:
    """Stable model boundary used by semantic workflows.

    Provider-specific transport stays behind ProviderAdapter. Ingest, lint, and
    query only depend on ChatClient semantics and never branch on vendor names.
    """

    adapter: ProviderAdapter

    @classmethod
    def from_config(
        cls,
        provider: str,
        config: ModelProviderConfig,
        *,
        timeout_seconds: float = 60.0,
    ) -> ModelGateway:
        if config.adapter == "ollama":
            return cls(
                OllamaNativeChatClient.from_config(
                    provider,
                    config,
                    timeout_seconds=timeout_seconds,
                )
            )
        return cls(
            OpenAICompatibleChatClient.from_config(
                provider,
                config,
                timeout_seconds=timeout_seconds,
            )
        )

    @property
    def provider(self) -> str:
        return self.adapter.provider

    @property
    def model(self) -> str:
        return self.adapter.model

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        return self.adapter.complete(request)

    def stream(self, request: ChatCompletionRequest) -> Iterator[ChatCompletionStreamChunk]:
        yield from self.adapter.stream(request)

    def check(self) -> ProviderHealthCheck:
        return self.adapter.check()

    def discover_models(self) -> ProviderModelDiscovery:
        return self.adapter.discover_models()


@dataclass(frozen=True)
class OpenAICompatibleChatClient:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 60.0
    json_mode: bool = True
    verify_tls: bool = True
    tls_ca_file: str | None = None
    configured_context_window: int | None = None
    configured_max_output_tokens: int | None = None
    extra_body: dict[str, object] | None = None

    @classmethod
    def from_config(
        cls,
        provider: str,
        config: ModelProviderConfig,
        *,
        timeout_seconds: float = 60.0,
    ) -> OpenAICompatibleChatClient:
        base_url = (config.base_url or "").rstrip("/")
        model = config.model or ""
        api_key = config.resolved_api_key() or ""
        if not base_url:
            raise UserInputError(f"Model provider {provider} is missing base_url")
        if not model:
            raise UserInputError(f"Model provider {provider} is missing model")
        return cls(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            json_mode=config.json_mode,
            verify_tls=True,
            tls_ca_file=str(config.tls_ca_file) if config.tls_ca_file else None,
            configured_context_window=config.context_window,
            configured_max_output_tokens=config.max_output_tokens,
            extra_body=config.extra_body,
        )

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [message.model_dump() for message in _merge_system_messages(request.messages)],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if self.json_mode and request.structured_output:
            payload["response_format"] = {"type": "json_object"}
        if self.extra_body:
            payload.update(self.extra_body)

        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(content_type=True),
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds, context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:  # noqa: S310
                raw_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ExternalServiceError(f"Model provider {self.provider} returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(f"Model provider {self.provider} request failed: {exc.reason}") from exc
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            raise ExternalServiceError(f"Model provider {self.provider} response was interrupted: {exc}") from exc

        try:
            data = json.loads(raw_text)
            content = _extract_openai_content(data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ModelOutputError(f"Model provider {self.provider} returned an invalid chat completion response: {exc}") from exc
        elapsed = time.perf_counter() - started
        usage = _extract_usage(data)
        return ChatCompletionResponse(
            content=content,
            provider=self.provider,
            model=self.model,
            raw=data,
            usage=usage,
            elapsed_seconds=elapsed,
            tokens_per_second=_tokens_per_second(usage, elapsed),
        )

    def stream(self, request: ChatCompletionRequest) -> Iterator[ChatCompletionStreamChunk]:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [message.model_dump() for message in _merge_system_messages(request.messages)],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if self.json_mode and request.structured_output:
            payload["response_format"] = {"type": "json_object"}
        if self.extra_body:
            payload.update(self.extra_body)

        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(content_type=True),
            method="POST",
        )
        started = time.perf_counter()
        content_parts: list[str] = []
        final_usage: dict[str, int] = {}
        final_raw: dict[str, object] = {"stream": True, "chunks": 0}
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds, context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:  # noqa: S310
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_text = line.removeprefix("data:").strip()
                    if data_text == "[DONE]":
                        break
                    try:
                        data = json.loads(data_text)
                    except json.JSONDecodeError as exc:
                        raise ModelOutputError(f"Model provider {self.provider} returned an invalid stream chunk: {exc}") from exc
                    final_raw["chunks"] = int(final_raw["chunks"]) + 1
                    usage = _extract_usage(data)
                    if usage:
                        final_usage.update(usage)
                    delta = _extract_openai_delta(data)
                    if delta:
                        content_parts.append(delta)
                        yield ChatCompletionStreamChunk(delta=delta)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ExternalServiceError(f"Model provider {self.provider} returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(f"Model provider {self.provider} request failed: {exc.reason}") from exc
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            raise ExternalServiceError(f"Model provider {self.provider} response was interrupted: {exc}") from exc
        content = "".join(content_parts).strip()
        if not content:
            raise ModelOutputError(f"Model provider {self.provider} returned an empty streamed chat completion.")
        elapsed = time.perf_counter() - started
        yield ChatCompletionStreamChunk(
            response=ChatCompletionResponse(
                content=content,
                provider=self.provider,
                model=self.model,
                raw=final_raw,
                usage=final_usage,
                elapsed_seconds=elapsed,
                tokens_per_second=_tokens_per_second(final_usage, elapsed),
            )
        )

    def check(self) -> ProviderHealthCheck:
        discovery = self.discover_models()
        return ProviderHealthCheck(
            available=discovery.available,
            structured_output=self.json_mode,
            message=discovery.message,
            details=discovery.details,
        )

    def discover_models(self) -> ProviderModelDiscovery:
        started = time.perf_counter()
        request = urllib.request.Request(
            f"{self.base_url}/models",
            headers=self._headers(content_type=False),
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_seconds, 5.0), context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:  # noqa: S310
                body = response.read().decode("utf-8", errors="replace")
                status_code = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return ProviderModelDiscovery(
                available=False,
                message=f"Provider endpoint returned HTTP {exc.code} for /models.",
                details={"status_code": exc.code, "body_preview": body[:500], "elapsed_seconds": round(time.perf_counter() - started, 3)},
            )
        except urllib.error.URLError as exc:
            return ProviderModelDiscovery(
                available=False,
                message=f"Provider endpoint request failed: {exc.reason}",
                details={"elapsed_seconds": round(time.perf_counter() - started, 3)},
            )
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout) as exc:
            return ProviderModelDiscovery(
                available=False,
                message=f"Provider endpoint check was interrupted: {exc}",
                details={"elapsed_seconds": round(time.perf_counter() - started, 3)},
            )

        model_details = _extract_model_list_details(body, self.model)
        detected_context_window = _detected_context_window_from_model_details(model_details)
        ollama_details = self._detect_ollama_model_details() if detected_context_window is None else {}
        if detected_context_window is None:
            detected_context_window = _int_or_none(ollama_details.get("detected_context_window"))
        return ProviderModelDiscovery(
            available=200 <= int(status_code) < 300,
            message="Provider endpoint responded to /models.",
            details={
                "status_code": int(status_code),
                "body_preview": body[:500],
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "configured_context_window": self.configured_context_window,
                "configured_max_output_tokens": self.configured_max_output_tokens,
                "detected_context_window": detected_context_window,
                "effective_context_window": detected_context_window or self.configured_context_window,
                "context_window_source": "runtime" if detected_context_window else "config" if self.configured_context_window else "unknown",
                **ollama_details,
                **model_details,
            },
        )

    def _headers(self, *, content_type: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _detect_ollama_model_details(self) -> dict[str, object]:
        if not _is_probably_ollama_endpoint(self.provider, self.base_url):
            return {}
        api_base = _ollama_api_base_url(self.base_url)
        request = urllib.request.Request(
            f"{api_base}/api/show",
            data=json.dumps({"model": self.model}, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(content_type=True),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_seconds, 5.0), context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:  # noqa: S310
                body = response.read().decode("utf-8", errors="replace")
                status_code = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {
                "ollama_show_available": False,
                "ollama_show_status_code": exc.code,
                "ollama_show_error": body[:300],
            }
        except urllib.error.URLError as exc:
            return {"ollama_show_available": False, "ollama_show_error": str(exc.reason)}
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout) as exc:
            return {"ollama_show_available": False, "ollama_show_error": str(exc)}

        context_window = _extract_ollama_context_window(body)
        return {
            "ollama_show_available": 200 <= int(status_code) < 300,
            "ollama_show_status_code": int(status_code),
            "detected_context_window": context_window,
            "ollama_show_body_preview": body[:500],
        }


@dataclass(frozen=True)
class OllamaNativeChatClient:
    provider: str
    base_url: str
    model: str
    timeout_seconds: float = 60.0
    json_mode: bool = True
    verify_tls: bool = True
    tls_ca_file: str | None = None
    configured_context_window: int | None = None
    configured_max_output_tokens: int | None = None
    extra_body: dict[str, object] | None = None

    @classmethod
    def from_config(
        cls,
        provider: str,
        config: ModelProviderConfig,
        *,
        timeout_seconds: float = 60.0,
    ) -> OllamaNativeChatClient:
        base_url = (config.base_url or "").rstrip("/")
        model = config.model or ""
        if not base_url:
            raise UserInputError(f"Model provider {provider} is missing base_url")
        if not model:
            raise UserInputError(f"Model provider {provider} is missing model")
        return cls(
            provider=provider,
            base_url=_ollama_api_base_url(base_url),
            model=model,
            timeout_seconds=timeout_seconds,
            json_mode=config.json_mode,
            verify_tls=True,
            tls_ca_file=str(config.tls_ca_file) if config.tls_ca_file else None,
            configured_context_window=config.context_window,
            configured_max_output_tokens=config.max_output_tokens,
            extra_body=config.extra_body,
        )

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        options: dict[str, object] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [message.model_dump() for message in _merge_system_messages(request.messages)],
            "stream": False,
            "think": False,
            "options": options,
        }
        if self.json_mode and request.structured_output:
            payload["format"] = "json"
        if self.extra_body:
            payload = _deep_merge_payload(payload, self.extra_body)

        http_request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds, context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:  # noqa: S310
                raw_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ExternalServiceError(f"Model provider {self.provider} returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(f"Model provider {self.provider} request failed: {exc.reason}") from exc
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            raise ExternalServiceError(f"Model provider {self.provider} response was interrupted: {exc}") from exc

        try:
            data = json.loads(raw_text)
            content = _extract_ollama_content(data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ModelOutputError(f"Model provider {self.provider} returned an invalid Ollama chat response: {exc}") from exc
        elapsed = time.perf_counter() - started
        usage = _extract_ollama_usage(data)
        return ChatCompletionResponse(
            content=content,
            provider=self.provider,
            model=self.model,
            raw=data,
            usage=usage,
            elapsed_seconds=elapsed,
            tokens_per_second=_ollama_tokens_per_second(data, usage, elapsed),
        )

    def stream(self, request: ChatCompletionRequest) -> Iterator[ChatCompletionStreamChunk]:
        options: dict[str, object] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [message.model_dump() for message in _merge_system_messages(request.messages)],
            "stream": True,
            "think": False,
            "options": options,
        }
        if self.json_mode and request.structured_output:
            payload["format"] = "json"
        if self.extra_body:
            payload = _deep_merge_payload(payload, self.extra_body)

        http_request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Accept": "application/x-ndjson, application/json", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        content_parts: list[str] = []
        final_data: dict[str, object] = {}
        chunks = 0
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds, context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:  # noqa: S310
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ModelOutputError(f"Model provider {self.provider} returned an invalid Ollama stream chunk: {exc}") from exc
                    chunks += 1
                    final_data = data
                    delta = _extract_ollama_delta(data)
                    if delta:
                        content_parts.append(delta)
                        yield ChatCompletionStreamChunk(delta=delta)
                    if data.get("done") is True:
                        break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ExternalServiceError(f"Model provider {self.provider} returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(f"Model provider {self.provider} request failed: {exc.reason}") from exc
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout, ssl.SSLError) as exc:
            raise ExternalServiceError(f"Model provider {self.provider} response was interrupted: {exc}") from exc
        content = "".join(content_parts).strip()
        if not content:
            raise ModelOutputError(f"Model provider {self.provider} returned an empty streamed Ollama chat response.")
        elapsed = time.perf_counter() - started
        usage = _extract_ollama_usage(final_data)
        yield ChatCompletionStreamChunk(
            response=ChatCompletionResponse(
                content=content,
                provider=self.provider,
                model=self.model,
                raw={"stream": True, "chunks": chunks, "final": final_data},
                usage=usage,
                elapsed_seconds=elapsed,
                tokens_per_second=_ollama_tokens_per_second(final_data, usage, elapsed),
            )
        )

    def check(self) -> ProviderHealthCheck:
        discovery = self.discover_models()
        return ProviderHealthCheck(
            available=discovery.available,
            structured_output=self.json_mode,
            message=discovery.message,
            details=discovery.details,
        )

    def discover_models(self) -> ProviderModelDiscovery:
        started = time.perf_counter()
        request = urllib.request.Request(
            f"{self.base_url}/api/tags",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_seconds, 5.0), context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:  # noqa: S310
                body = response.read().decode("utf-8", errors="replace")
                status_code = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return ProviderModelDiscovery(
                available=False,
                message=f"Ollama endpoint returned HTTP {exc.code} for /api/tags.",
                details={"status_code": exc.code, "body_preview": body[:500], "elapsed_seconds": round(time.perf_counter() - started, 3)},
            )
        except urllib.error.URLError as exc:
            return ProviderModelDiscovery(
                available=False,
                message=f"Ollama endpoint request failed: {exc.reason}",
                details={"elapsed_seconds": round(time.perf_counter() - started, 3)},
            )
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout) as exc:
            return ProviderModelDiscovery(
                available=False,
                message=f"Ollama endpoint check was interrupted: {exc}",
                details={"elapsed_seconds": round(time.perf_counter() - started, 3)},
            )

        model_details = _extract_ollama_model_list_details(body, self.model)
        show_details = self._detect_ollama_model_details()
        detected_context_window = _int_or_none(show_details.get("detected_context_window"))
        return ProviderModelDiscovery(
            available=200 <= int(status_code) < 300,
            message="Ollama endpoint responded to /api/tags.",
            details={
                "status_code": int(status_code),
                "body_preview": body[:500],
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "configured_context_window": self.configured_context_window,
                "configured_max_output_tokens": self.configured_max_output_tokens,
                "detected_context_window": detected_context_window,
                "effective_context_window": detected_context_window or self.configured_context_window,
                "context_window_source": "runtime" if detected_context_window else "config" if self.configured_context_window else "unknown",
                **model_details,
                **show_details,
            },
        )

    def _detect_ollama_model_details(self) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self.base_url}/api/show",
            data=json.dumps({"model": self.model}, ensure_ascii=False).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout_seconds, 5.0), context=_ssl_context(self.verify_tls, self.tls_ca_file)) as response:  # noqa: S310
                body = response.read().decode("utf-8", errors="replace")
                status_code = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {
                "ollama_show_available": False,
                "ollama_show_status_code": exc.code,
                "ollama_show_error": body[:300],
            }
        except urllib.error.URLError as exc:
            return {"ollama_show_available": False, "ollama_show_error": str(exc.reason)}
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, TimeoutError, socket.timeout) as exc:
            return {"ollama_show_available": False, "ollama_show_error": str(exc)}

        return {
            "ollama_show_available": 200 <= int(status_code) < 300,
            "ollama_show_status_code": int(status_code),
            "detected_context_window": _extract_ollama_context_window(body),
            "ollama_show_body_preview": body[:500],
        }


def _ssl_context(verify_tls: bool, tls_ca_file: str | None = None) -> ssl.SSLContext:
    if not verify_tls:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    return ssl.create_default_context(cafile=tls_ca_file or certifi.where())


def _deep_merge_payload(base: dict[str, object], extra: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in extra.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = {**current, **value}
        else:
            merged[key] = value
    return merged


def _merge_system_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Normalize chat payloads for providers that accept only one system message.

    KnoArbor keeps system concerns separate internally: stable task prompt,
    workspace context, memory context, and provider probes are assembled by
    different layers. Provider adapters own wire-level compatibility, so they
    collapse those system sections into one ordered system message before
    sending OpenAI-compatible/Ollama payloads.
    """

    system_messages = [message for message in messages if message.role == "system"]
    if len(system_messages) <= 1:
        return messages
    merged_system = ChatMessage(
        role="system",
        content="\n\n".join(
            f"## System Context {index}\n{message.content}"
            for index, message in enumerate(system_messages, start=1)
        ),
    )
    output: list[ChatMessage] = []
    inserted = False
    for message in messages:
        if message.role == "system":
            if not inserted:
                output.append(merged_system)
                inserted = True
            continue
        output.append(message)
    return output


def is_local_or_private_model_endpoint(base_url: str | None) -> bool:
    if not base_url:
        return False
    try:
        host = urllib.parse.urlparse(base_url).hostname
    except ValueError:
        return False
    if not host:
        return False
    normalized = host.lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return address.is_private or address.is_loopback


def _extract_openai_content(data: object) -> str:
    if not isinstance(data, dict):
        raise SemanticContractError("Model response must be a JSON object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SemanticContractError("Model response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise SemanticContractError("Model response choice must be an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise SemanticContractError("Model response choice missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise SemanticContractError("Model response message content is empty")
    return content


def _extract_openai_delta(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        return content if isinstance(content, str) else ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        return content if isinstance(content, str) else ""
    return ""


def _extract_ollama_content(data: object) -> str:
    if not isinstance(data, dict):
        raise SemanticContractError("Ollama response must be a JSON object")
    message = data.get("message")
    if not isinstance(message, dict):
        raise SemanticContractError("Ollama response missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise SemanticContractError("Ollama response message content is empty")
    return content


def _extract_ollama_delta(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    message = data.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        return content if isinstance(content, str) else ""
    response = data.get("response")
    return response if isinstance(response, str) else ""


def _extract_usage(data: object) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return {}
    result: dict[str, int] = {}
    for source_key, target_key in (
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
        ("prompt_cache_hit_tokens", "prompt_cache_hit_tokens"),
        ("prompt_cache_miss_tokens", "prompt_cache_miss_tokens"),
    ):
        value = usage.get(source_key)
        if isinstance(value, int):
            result[target_key] = value
    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        cached_tokens = prompt_details.get("cached_tokens")
        if isinstance(cached_tokens, int):
            result["prompt_cached_tokens"] = cached_tokens
    return result


def _extract_ollama_usage(data: object) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    prompt_tokens = _int_or_none(data.get("prompt_eval_count"))
    completion_tokens = _int_or_none(data.get("eval_count"))
    result: dict[str, int] = {}
    if prompt_tokens is not None:
        result["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        result["completion_tokens"] = completion_tokens
    if prompt_tokens is not None or completion_tokens is not None:
        result["total_tokens"] = (prompt_tokens or 0) + (completion_tokens or 0)
    return result


def _extract_model_list_details(body: str, configured_model: str) -> dict[str, object]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"models_list_valid": False, "model_ids": [], "configured_model_found": False}
    if not isinstance(payload, dict):
        return {"models_list_valid": False, "model_ids": [], "configured_model_found": False}
    data = payload.get("data")
    if not isinstance(data, list):
        return {"models_list_valid": False, "model_ids": [], "configured_model_found": False}
    model_items = [item for item in data if isinstance(item, dict)]
    model_ids = [
        item.get("id")
        for item in model_items
        if isinstance(item.get("id"), str) and item.get("id")
    ]
    configured_item = next((item for item in model_items if item.get("id") == configured_model), None)
    detected_context_window = _extract_context_window_from_model_item(configured_item) if configured_item else None
    return {
        "models_list_valid": True,
        "model_ids": model_ids[:100],
        "model_count": len(model_ids),
        "configured_model_found": configured_model in model_ids,
        "configured_model_max_model_len": detected_context_window,
    }


def _extract_ollama_model_list_details(body: str, configured_model: str) -> dict[str, object]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"models_list_valid": False, "model_ids": [], "configured_model_found": False}
    if not isinstance(payload, dict):
        return {"models_list_valid": False, "model_ids": [], "configured_model_found": False}
    models = payload.get("models")
    if not isinstance(models, list):
        return {"models_list_valid": False, "model_ids": [], "configured_model_found": False}
    model_items = [item for item in models if isinstance(item, dict)]
    model_ids = [
        item.get("name") or item.get("model")
        for item in model_items
        if isinstance(item.get("name") or item.get("model"), str) and (item.get("name") or item.get("model"))
    ]
    return {
        "models_list_valid": True,
        "model_ids": model_ids[:100],
        "model_count": len(model_ids),
        "configured_model_found": configured_model in model_ids,
    }


def _detected_context_window_from_model_details(details: dict[str, object]) -> int | None:
    return _int_or_none(details.get("configured_model_max_model_len"))


def _extract_context_window_from_model_item(item: dict[str, object] | None) -> int | None:
    if not item:
        return None
    direct_keys = (
        "max_model_len",
        "max_sequence_length",
        "max_seq_len",
        "context_length",
        "context_window",
        "n_ctx",
    )
    for key in direct_keys:
        value = _int_or_none(item.get(key))
        if value:
            return value
    for container_key in ("metadata", "config", "model_info"):
        nested = item.get(container_key)
        if isinstance(nested, dict):
            value = _extract_context_window_from_model_info(nested)
            if value:
                return value
    return None


def _extract_ollama_context_window(body: str) -> int | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("model_info", "details", "info"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            value = _extract_context_window_from_model_info(nested)
            if value:
                return value
    options = payload.get("options")
    if isinstance(options, dict):
        value = _int_or_none(options.get("num_ctx"))
        if value:
            return value
    parameters = payload.get("parameters")
    if isinstance(parameters, str):
        value = _extract_num_ctx_from_parameters(parameters)
        if value:
            return value
    return None


def _extract_context_window_from_model_info(model_info: dict[object, object]) -> int | None:
    preferred_suffixes = (
        "context_length",
        "max_position_embeddings",
        "max_sequence_length",
        "max_seq_len",
        "max_model_len",
        "n_ctx",
        "num_ctx",
    )
    for key, value in model_info.items():
        if not isinstance(key, str):
            continue
        normalized = key.lower().replace("-", "_")
        if normalized in preferred_suffixes or any(normalized.endswith(f".{suffix}") for suffix in preferred_suffixes):
            parsed = _int_or_none(value)
            if parsed:
                return parsed
    return None


def _extract_num_ctx_from_parameters(parameters: str) -> int | None:
    for line in parameters.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "num_ctx":
            value = _int_or_none(parts[1])
            if value:
                return value
    return None


def _is_probably_ollama_endpoint(provider: str, base_url: str) -> bool:
    if "ollama" in provider.lower():
        return True
    parsed = urllib.parse.urlparse(base_url)
    return parsed.port == 11434


def _ollama_api_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    path = parsed.path.rstrip("/")
    if path == "/v1":
        path = ""
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer():
        parsed = int(value)
        return parsed if parsed > 0 else None
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _tokens_per_second(usage: dict[str, int], elapsed_seconds: float) -> float | None:
    completion_tokens = usage.get("completion_tokens")
    if not completion_tokens or elapsed_seconds <= 0:
        return None
    return completion_tokens / elapsed_seconds


def _ollama_tokens_per_second(data: object, usage: dict[str, int], elapsed_seconds: float) -> float | None:
    if isinstance(data, dict):
        eval_duration = _int_or_none(data.get("eval_duration"))
        completion_tokens = usage.get("completion_tokens")
        if eval_duration and completion_tokens:
            seconds = eval_duration / 1_000_000_000
            if seconds > 0:
                return completion_tokens / seconds
    return _tokens_per_second(usage, elapsed_seconds)
