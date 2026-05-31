from __future__ import annotations

import json
import http.client
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

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


class ChatCompletionResponse(BaseModel):
    content: str
    provider: str
    model: str
    raw: dict[str, object] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    elapsed_seconds: float = 0.0
    tokens_per_second: float | None = None


class ChatClient(Protocol):
    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        ...


@dataclass(frozen=True)
class OpenAICompatibleChatClient:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 60.0
    json_mode: bool = True

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
        api_key = config.api_key() or ""
        if not base_url:
            raise UserInputError(f"Model provider {provider} is missing base_url")
        if not model:
            raise UserInputError(f"Model provider {provider} is missing model")
        if not api_key:
            raise UserInputError(f"Model provider {provider} is missing API key")
        return cls(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            json_mode=config.json_mode,
        )

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ExternalServiceError(f"Model provider {self.provider} returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ExternalServiceError(f"Model provider {self.provider} request failed: {exc.reason}") from exc
        except (http.client.IncompleteRead, TimeoutError, socket.timeout) as exc:
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


def _tokens_per_second(usage: dict[str, int], elapsed_seconds: float) -> float | None:
    completion_tokens = usage.get("completion_tokens")
    if not completion_tokens or elapsed_seconds <= 0:
        return None
    return completion_tokens / elapsed_seconds
