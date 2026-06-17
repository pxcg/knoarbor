from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from knoarbor.core.config import ModelRetryConfig
from knoarbor.core.errors import KnoArborError, ModelOutputError
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatCompletionResponse


@dataclass(frozen=True)
class ChatModelCallResult:
    completion: ChatCompletionResponse
    call_record: dict[str, object]


def run_chat_model_call(
    *,
    client: ChatClient,
    request: ChatCompletionRequest,
    retry: ModelRetryConfig,
    phase: str,
    turn: int,
    prompt_chars: int,
) -> ChatModelCallResult:
    attempts = max(1, retry.max_attempts if retry.enabled else 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            completion = client.complete(request)
            return ChatModelCallResult(
                completion=completion,
                call_record=_call_record(
                    completion,
                    phase=phase,
                    turn=turn,
                    prompt_chars=prompt_chars,
                    attempt=attempt,
                    max_attempts=attempts,
                    elapsed_seconds=completion.elapsed_seconds or round(time.perf_counter() - started, 3),
                ),
            )
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _should_retry(exc, retry):
                raise
            if retry.backoff_seconds > 0:
                time.sleep(retry.backoff_seconds)
    assert last_error is not None
    raise last_error


def run_chat_model_call_stream(
    *,
    client: ChatClient,
    request: ChatCompletionRequest,
    retry: ModelRetryConfig,
    phase: str,
    turn: int,
    prompt_chars: int,
    on_delta: Callable[[str], None] | None = None,
) -> ChatModelCallResult:
    attempts = max(1, retry.max_attempts if retry.enabled else 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            stream = getattr(client, "stream", None)
            if not callable(stream):
                completion = client.complete(request)
                if on_delta and completion.content:
                    on_delta(completion.content)
            else:
                completion = None
                for chunk in stream(request):
                    if chunk.delta and on_delta:
                        on_delta(chunk.delta)
                    if chunk.response is not None:
                        completion = chunk.response
                if completion is None:
                    raise ModelOutputError("Model stream ended without a final completion response.")
            return ChatModelCallResult(
                completion=completion,
                call_record=_call_record(
                    completion,
                    phase=phase,
                    turn=turn,
                    prompt_chars=prompt_chars,
                    attempt=attempt,
                    max_attempts=attempts,
                    elapsed_seconds=completion.elapsed_seconds or round(time.perf_counter() - started, 3),
                ),
            )
        except Exception as exc:
            last_error = exc
            if attempt >= attempts or not _should_retry(exc, retry):
                raise
            if retry.backoff_seconds > 0:
                time.sleep(retry.backoff_seconds)
    assert last_error is not None
    raise last_error


def _call_record(
    completion: ChatCompletionResponse,
    *,
    phase: str,
    turn: int,
    prompt_chars: int,
    attempt: int,
    max_attempts: int,
    elapsed_seconds: float,
) -> dict[str, object]:
    return {
        **completion.usage,
        "provider": completion.provider,
        "model": completion.model,
        "turn": turn,
        "phase": phase,
        "prompt_chars": prompt_chars,
        "elapsed_seconds": elapsed_seconds,
        "tokens_per_second": completion.tokens_per_second,
        "attempt": attempt,
        "max_attempts": max_attempts,
    }


def _should_retry(exc: Exception, retry: ModelRetryConfig) -> bool:
    if isinstance(exc, ModelOutputError):
        return retry.retry_on_invalid_output and _code_retryable(exc.code, retry)
    if isinstance(exc, KnoArborError):
        return exc.retryable and _code_retryable(exc.code, retry)
    return False


def _code_retryable(code: str, retry: ModelRetryConfig) -> bool:
    return not retry.retryable_error_codes or code in retry.retryable_error_codes
