from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from pydantic import ValidationError

from knoarbor.core.errors import KnoArborError, ModelOutputError, error_info

from knoarbor.semantic.contracts import SemanticContract, load_semantic_contract
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatMessage
from knoarbor.runtime import RunReporter


SEMANTIC_EXECUTOR_SYSTEM_PROMPT = (
    "You are KnoArbor's semantic contract executor. "
    "Follow the stable contract instructions in the next message exactly, "
    "then apply them to the dynamic payload. Return only the required JSON."
)


@dataclass(frozen=True)
class SemanticRetryPolicy:
    enabled: bool = True
    max_attempts: int = 2
    backoff_seconds: float = 2.0
    retry_on_invalid_output: bool = True
    retryable_error_codes: frozenset[str] = frozenset({"KA-EXT-001", "KA-MODEL-001", "KA-SEM-001", "KA-STORAGE-001"})

    @property
    def attempts(self) -> int:
        if not self.enabled:
            return 1
        return max(1, self.max_attempts)


class SemanticRunResult(BaseModel):
    contract_name: str
    schema_version: str
    provider: str
    model: str
    output: BaseModel
    metrics: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class SemanticRunFailure:
    contract_name: str
    schema_version: str
    provider: str
    model: str
    metrics: dict[str, object]


@dataclass(frozen=True)
class SemanticPromptPackage:
    """Prompt package with a stable cacheable prefix and dynamic payload tail."""

    messages: list[ChatMessage]
    stable_chars: int
    dynamic_chars: int
    stable_message_count: int
    dynamic_message_count: int


class SemanticRunner:
    def __init__(self, client: ChatClient, retry_policy: SemanticRetryPolicy | None = None) -> None:
        self.client = client
        self.retry_policy = retry_policy or SemanticRetryPolicy()
        self.history: list[SemanticRunResult | SemanticRunFailure] = []

    def run(
        self,
        contract_name: str,
        payload: dict[str, Any],
        *,
        user_instruction: str | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> SemanticRunResult:
        contract = load_semantic_contract(contract_name)
        prompt_package = build_semantic_prompt_package(contract, payload, user_instruction=user_instruction)
        payload_char_breakdown = semantic_payload_char_breakdown(payload)
        request = ChatCompletionRequest(
            messages=prompt_package.messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        last_error: Exception | None = None
        attempts = self.retry_policy.attempts
        for attempt in range(1, attempts + 1):
            try:
                return self._run_once(
                    contract,
                    request,
                    prompt_package,
                    payload_char_breakdown=payload_char_breakdown,
                    attempt=attempt,
                    max_attempts=attempts,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not self._should_retry(exc):
                    raise
                self._emit_retry_event(contract, exc, attempt=attempt, max_attempts=attempts)
                self._sleep_before_retry()
        assert last_error is not None
        raise last_error

    def _run_once(
        self,
        contract: SemanticContract,
        request: ChatCompletionRequest,
        prompt_package: SemanticPromptPackage,
        *,
        payload_char_breakdown: dict[str, int],
        attempt: int,
        max_attempts: int,
    ) -> SemanticRunResult:
        reporter = RunReporter.current()
        reporter.model_call_started(
            contract_name=contract.name,
            schema_version=contract.schema_version,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        started = time.perf_counter()
        try:
            response = self.client.complete(request)
        except Exception as exc:
            elapsed = time.perf_counter() - started
            metrics = self._failure_metrics(exc, elapsed_seconds=elapsed)
            self.history.append(
                SemanticRunFailure(
                    contract_name=contract.name,
                    schema_version=contract.schema_version,
                    provider=str(metrics.get("provider") or ""),
                    model=str(metrics.get("model") or ""),
                    metrics=metrics,
                )
            )
            reporter.model_call_failed(
                contract_name=contract.name,
                schema_version=contract.schema_version,
                attempt=attempt,
                max_attempts=max_attempts,
                error=exc,
                elapsed_seconds=elapsed,
            )
            raise
        reporter.model_call_finished(
            contract_name=contract.name,
            provider=response.provider,
            model=response.model,
            usage=response.usage,
            elapsed_seconds=response.elapsed_seconds,
            tokens_per_second=response.tokens_per_second,
        )
        metrics = {
            "provider": response.provider,
            "model": response.model,
            "prompt_stable_chars": prompt_package.stable_chars,
            "prompt_dynamic_chars": prompt_package.dynamic_chars,
            "prompt_stable_message_count": prompt_package.stable_message_count,
            "prompt_dynamic_message_count": prompt_package.dynamic_message_count,
            "payload_char_breakdown": payload_char_breakdown,
            "payload_char_total": sum(payload_char_breakdown.values()),
            "payload_top_field": _payload_top_field(payload_char_breakdown),
            "prompt_tokens": response.usage.get("prompt_tokens", 0),
            "prompt_cached_tokens": response.usage.get("prompt_cached_tokens", 0),
            "prompt_cache_hit_tokens": response.usage.get("prompt_cache_hit_tokens", 0),
            "prompt_cache_miss_tokens": response.usage.get("prompt_cache_miss_tokens", 0),
            "completion_tokens": response.usage.get("completion_tokens", 0),
            "total_tokens": response.usage.get("total_tokens", 0),
            "elapsed_seconds": response.elapsed_seconds,
            "tokens_per_second": response.tokens_per_second,
        }
        try:
            parsed = parse_contract_output(contract, response.content)
        except Exception as exc:
            info = error_info(exc)
            metrics["error_type"] = type(exc).__name__
            metrics["error_message"] = str(exc)
            metrics["error_code"] = info["code"]
            metrics["error_category"] = info["category"]
            metrics["error_retryable"] = info["retryable"]
            metrics["error_hint"] = info["hint"]
            self.history.append(
                SemanticRunFailure(
                    contract_name=contract.name,
                    schema_version=contract.schema_version,
                    provider=response.provider,
                    model=response.model,
                    metrics=metrics,
                )
            )
            reporter.model_output_invalid(
                contract_name=contract.name,
                schema_version=contract.schema_version,
                attempt=attempt,
                max_attempts=max_attempts,
                error=exc,
            )
            raise
        result = SemanticRunResult(
            contract_name=contract.name,
            schema_version=contract.schema_version,
            provider=response.provider,
            model=response.model,
            output=parsed,
            metrics=metrics,
        )
        self.history.append(result)
        return result

    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, (ModelOutputError, ValidationError)):
            return self.retry_policy.retry_on_invalid_output and self._code_retryable("KA-MODEL-001")
        if isinstance(exc, KnoArborError):
            return bool(exc.retryable) and self._code_retryable(exc.code)
        if isinstance(exc, json.JSONDecodeError):
            return self.retry_policy.retry_on_invalid_output and self._code_retryable("KA-MODEL-001")
        return False

    def _code_retryable(self, code: str) -> bool:
        return not self.retry_policy.retryable_error_codes or code in self.retry_policy.retryable_error_codes

    def _emit_retry_event(self, contract: SemanticContract, exc: Exception, *, attempt: int, max_attempts: int) -> None:
        RunReporter.current().model_call_retrying(
            contract_name=contract.name,
            schema_version=contract.schema_version,
            attempt=attempt + 1,
            max_attempts=max_attempts,
            previous_error=exc,
            backoff_seconds=self.retry_policy.backoff_seconds,
        )

    def _sleep_before_retry(self) -> None:
        if self.retry_policy.backoff_seconds <= 0:
            return
        time.sleep(self.retry_policy.backoff_seconds)
        RunReporter.current().raise_if_cancelled()

    def _failure_metrics(self, exc: Exception, *, elapsed_seconds: float) -> dict[str, object]:
        info = error_info(exc)
        return {
            "provider": getattr(self.client, "provider", self.client.__class__.__name__),
            "model": getattr(self.client, "model", ""),
            "prompt_stable_chars": 0,
            "prompt_dynamic_chars": 0,
            "prompt_stable_message_count": 0,
            "prompt_dynamic_message_count": 0,
            "payload_char_breakdown": {},
            "payload_char_total": 0,
            "payload_top_field": None,
            "prompt_tokens": 0,
            "prompt_cached_tokens": 0,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "elapsed_seconds": elapsed_seconds,
            "tokens_per_second": None,
            "error_code": info["code"],
            "error_category": info["category"],
            "error_retryable": info["retryable"],
            "error_hint": info["hint"],
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def semantic_payload_char_breakdown(payload: dict[str, Any]) -> dict[str, int]:
    """Return top-level dynamic payload sizes using the same JSON encoding as prompts."""

    breakdown: dict[str, int] = {}
    for key, value in payload.items():
        try:
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            rendered = str(value)
        breakdown[str(key)] = len(rendered)
    return breakdown


def _payload_top_field(breakdown: dict[str, int]) -> str | None:
    if not breakdown:
        return None
    return max(breakdown.items(), key=lambda item: item[1])[0]


def parse_contract_output(contract: SemanticContract, text: str) -> BaseModel:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelOutputError(f"Semantic contract {contract.name} returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelOutputError("Semantic contract output must be a JSON object")
    output = _contract_payload(contract, data)
    if not isinstance(output, dict):
        raise ModelOutputError("Semantic contract output must contain an object field named output")
    return contract.schema_model.model_validate(output)


def _contract_payload(contract: SemanticContract, data: dict[str, Any]) -> dict[str, Any] | None:
    output = data.get("output")
    if isinstance(output, dict):
        return output
    if data.get("schema_version") == contract.schema_version:
        return data
    return None


def _build_user_content(payload: dict[str, Any], user_instruction: str | None) -> str:
    lines = []
    if user_instruction:
        lines.extend([user_instruction.strip(), ""])
    lines.extend(["Input JSON:", json.dumps(payload, ensure_ascii=False, indent=2)])
    return "\n".join(lines)


def build_semantic_prompt_package(
    contract: SemanticContract,
    payload: dict[str, Any],
    *,
    user_instruction: str | None = None,
) -> SemanticPromptPackage:
    stable_messages = [
        ChatMessage(role="system", content=SEMANTIC_EXECUTOR_SYSTEM_PROMPT),
        ChatMessage(role="user", content=_cacheable_contract_preamble(contract)),
    ]
    dynamic_messages = [
        ChatMessage(role="user", content=_build_user_content(payload, user_instruction)),
    ]
    return SemanticPromptPackage(
        messages=[*stable_messages, *dynamic_messages],
        stable_chars=sum(len(message.content) for message in stable_messages),
        dynamic_chars=sum(len(message.content) for message in dynamic_messages),
        stable_message_count=len(stable_messages),
        dynamic_message_count=len(dynamic_messages),
    )


def _cacheable_contract_preamble(contract: SemanticContract) -> str:
    return (
        "Stable semantic contract package.\n\n"
        "Contract instructions:\n"
        f"{contract.prompt_text.strip()}\n\n"
        "Stable contract execution preamble.\n"
        f"- contract_name: {contract.name}\n"
        f"- schema_version: {contract.schema_version}\n"
        "- Return only valid JSON for the declared contract.\n"
        "- The dynamic source payload appears in the next message.\n"
        "- Treat this message as stable cacheable contract text."
    )
