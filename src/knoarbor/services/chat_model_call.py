from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable

from knoarbor.core.config import ModelRetryConfig
from knoarbor.core.errors import KnoArborError, ModelOutputError
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatCompletionResponse, ChatMessage

LOGGER = logging.getLogger(__name__)


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
    raise_if_cancelled: Callable[[], None] | None = None,
    before_model_call: Callable[[int], None] | None = None,
    completion_validator: Callable[[ChatCompletionResponse], None] | None = None,
) -> ChatModelCallResult:
    attempts = max(1, retry.max_attempts if retry.enabled else 1)
    last_error: Exception | None = None
    attempt_request = request
    attempt_prompt_chars = prompt_chars
    for attempt in range(1, attempts + 1):
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        if before_model_call is not None:
            before_model_call(attempt_prompt_chars)
        started = time.perf_counter()
        try:
            completion = client.complete(attempt_request)
            if raise_if_cancelled is not None:
                raise_if_cancelled()
            if completion_validator is not None:
                completion_validator(completion)
            return ChatModelCallResult(
                completion=completion,
                call_record=_call_record(
                    completion,
                    phase=phase,
                    turn=turn,
                    prompt_chars=attempt_prompt_chars,
                    attempt=attempt,
                    max_attempts=attempts,
                    elapsed_seconds=completion.elapsed_seconds or round(time.perf_counter() - started, 3),
                ),
            )
        except Exception as exc:
            last_error = exc
            _log_rejected_attempt(
                phase=phase,
                turn=turn,
                attempt=attempt,
                max_attempts=attempts,
                exc=exc,
            )
            if attempt >= attempts or not _should_retry(exc, retry):
                raise
            if isinstance(exc, ModelOutputError):
                attempt_request = _corrected_request(request, exc)
                attempt_prompt_chars = sum(len(message.content) for message in attempt_request.messages)
            if retry.backoff_seconds > 0:
                time.sleep(retry.backoff_seconds)
                if raise_if_cancelled is not None:
                    raise_if_cancelled()
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
    raise_if_cancelled: Callable[[], None] | None = None,
    before_model_call: Callable[[int], None] | None = None,
    completion_validator: Callable[[ChatCompletionResponse], None] | None = None,
) -> ChatModelCallResult:
    attempts = max(1, retry.max_attempts if retry.enabled else 1)
    last_error: Exception | None = None
    attempt_request = request
    attempt_prompt_chars = prompt_chars
    for attempt in range(1, attempts + 1):
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        if before_model_call is not None:
            before_model_call(attempt_prompt_chars)
        started = time.perf_counter()
        try:
            stream = getattr(client, "stream", None)
            if not callable(stream):
                completion = client.complete(attempt_request)
                if raise_if_cancelled is not None:
                    raise_if_cancelled()
                if on_delta and completion.content:
                    on_delta(completion.content)
            else:
                completion = None
                for chunk in stream(attempt_request):
                    if raise_if_cancelled is not None:
                        raise_if_cancelled()
                    if chunk.delta and on_delta:
                        on_delta(chunk.delta)
                    if chunk.response is not None:
                        completion = chunk.response
                if completion is None:
                    raise ModelOutputError("Model stream ended without a final completion response.")
            if completion_validator is not None:
                completion_validator(completion)
            return ChatModelCallResult(
                completion=completion,
                call_record=_call_record(
                    completion,
                    phase=phase,
                    turn=turn,
                    prompt_chars=attempt_prompt_chars,
                    attempt=attempt,
                    max_attempts=attempts,
                    elapsed_seconds=completion.elapsed_seconds or round(time.perf_counter() - started, 3),
                ),
            )
        except Exception as exc:
            last_error = exc
            _log_rejected_attempt(
                phase=phase,
                turn=turn,
                attempt=attempt,
                max_attempts=attempts,
                exc=exc,
            )
            if attempt >= attempts or not _should_retry(exc, retry):
                raise
            if isinstance(exc, ModelOutputError):
                attempt_request = _corrected_request(request, exc)
                attempt_prompt_chars = sum(len(message.content) for message in attempt_request.messages)
            if retry.backoff_seconds > 0:
                time.sleep(retry.backoff_seconds)
                if raise_if_cancelled is not None:
                    raise_if_cancelled()
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


def _log_rejected_attempt(
    *,
    phase: str,
    turn: int,
    attempt: int,
    max_attempts: int,
    exc: Exception,
) -> None:
    code = exc.code if isinstance(exc, KnoArborError) else type(exc).__name__
    detail = _bounded_diagnostic_detail(exc)
    LOGGER.warning(
        "chat_model_attempt_rejected phase=%s turn=%s attempt=%s max_attempts=%s code=%s detail=%s",
        phase,
        turn,
        attempt,
        max_attempts,
        code,
        detail,
    )


def _bounded_diagnostic_detail(exc: Exception) -> str:
    detail = " ".join(str(exc).split())
    detail = re.sub(
        r", input_value=.*?, input_type=[^\]]+\]",
        ", input_value=<redacted>]",
        detail,
    )
    return detail[:800]


def _corrected_request(request: ChatCompletionRequest, exc: ModelOutputError) -> ChatCompletionRequest:
    detail = " ".join(str(exc).split())[:800]
    correction = ChatMessage(
        role="user",
        content=(
            "The previous completion was rejected by the output contract. "
            f"Correct this violation and return the complete JSON object again: {detail}"
        ),
    )
    return request.model_copy(update={"messages": [*request.messages, correction]})
