from __future__ import annotations

import json

from knoarbor.semantic import ChatCompletionRequest, ChatCompletionResponse


class ScriptedChatClient:
    """Deterministic chat client for semantic contract and workflow tests."""

    def __init__(self, outputs: list[dict[str, object] | str | Exception]) -> None:
        self.outputs = list(outputs)
        self.requests: list[ChatCompletionRequest] = []
        self.calls = 0

    @classmethod
    def single(cls, output: dict[str, object] | str) -> "ScriptedChatClient":
        return cls([output])

    def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self.requests.append(request)
        self.calls += 1
        if not self.outputs:
            raise AssertionError("No scripted model outputs left")
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        return ChatCompletionResponse(content=content, provider="fake", model="unit", elapsed_seconds=0.01)

    @property
    def last_request(self) -> ChatCompletionRequest | None:
        return self.requests[-1] if self.requests else None
