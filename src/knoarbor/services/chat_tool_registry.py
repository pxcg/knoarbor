from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from knoarbor.core.schemas.chat import ChatToolTraceItem
from knoarbor.services.chat_tool_context import ChatToolContext


ChatToolHandler = Callable[[ChatToolContext, dict[str, Any]], ChatToolTraceItem]


@dataclass(frozen=True)
class ChatToolRegistry:
    handlers: dict[str, ChatToolHandler]
    fallback_handler: ChatToolHandler

    def execute(self, context: ChatToolContext, tool_name: str, arguments: dict[str, Any]) -> ChatToolTraceItem:
        return self.handlers.get(tool_name, self.fallback_handler)(context, arguments)
