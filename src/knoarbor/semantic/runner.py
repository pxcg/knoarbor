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
        request = ChatCompletionRequest(
            messages=[
                ChatMessage(role="system", content=contract.prompt_text),
                ChatMessage(role="user", content=_build_user_content(payload, user_instruction)),
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        last_error: Exception | None = None
        attempts = self.retry_policy.attempts
        for attempt in range(1, attempts + 1):
            try:
                return self._run_once(contract, request, attempt=attempt, max_attempts=attempts)
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
        *,
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
