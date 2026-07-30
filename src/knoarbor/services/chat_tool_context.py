from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from knoarbor.core.schemas.chat import ChatRequest
from knoarbor.services.chat_dependencies import ChatToolDependencies


@dataclass(frozen=True)
class ChatToolContext:
    request: ChatRequest
    services: ChatToolDependencies
    raise_if_cancelled: Callable[[], None] | None = None
