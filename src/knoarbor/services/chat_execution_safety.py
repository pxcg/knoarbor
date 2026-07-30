from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


class ChatExecutionSafetyExceeded(RuntimeError):
    def __init__(self, reason: str, usage: dict[str, object]) -> None:
        super().__init__(f"Chat execution safety limit reached: {reason}")
        self.reason = reason
        self.usage = usage


@dataclass
class ChatExecutionSafety:
    """Central runtime envelope; semantic stage counts are fixed by orchestration."""

    max_wall_seconds: float
    max_accumulated_bytes: int = 256 * 1024 * 1024
    max_result_memory_bytes: int = 128 * 1024 * 1024
    started_at: float = field(default_factory=time.monotonic)
    model_calls: int = 0
    tool_calls: int = 0
    accumulated_bytes: int = 0
    peak_result_bytes: int = 0

    def check(self) -> None:
        if time.monotonic() - self.started_at > self.max_wall_seconds:
            self._raise("wall_time")

    def before_model_call(self, _prompt_chars: int) -> None:
        self.check()
        self.model_calls += 1

    def before_tool_call(self) -> None:
        self.check()
        self.tool_calls += 1

    def ensure_tool_capacity(self) -> None:
        self.check()

    def observe_tool_result(self, result: dict[str, object]) -> None:
        encoded_bytes = len(json.dumps(result, ensure_ascii=False, default=str).encode("utf-8"))
        self.accumulated_bytes += encoded_bytes
        self.peak_result_bytes = max(self.peak_result_bytes, encoded_bytes)
        if self.accumulated_bytes > self.max_accumulated_bytes:
            self._raise("accumulated_bytes")
        if encoded_bytes > self.max_result_memory_bytes:
            self._raise("result_memory")
        self.check()

    def payload(self, *, stop_reason: str = "") -> dict[str, object]:
        return {
            "wall_seconds": round(time.monotonic() - self.started_at, 3),
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "accumulated_bytes": self.accumulated_bytes,
            "peak_result_bytes": self.peak_result_bytes,
            "limits": {
                "max_wall_seconds": self.max_wall_seconds,
                "max_accumulated_bytes": self.max_accumulated_bytes,
                "max_result_memory_bytes": self.max_result_memory_bytes,
            },
            "stop_reason": stop_reason,
        }

    def _raise(self, reason: str) -> None:
        raise ChatExecutionSafetyExceeded(reason, self.payload(stop_reason=reason))
