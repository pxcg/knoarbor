from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from knoarbor.core.schemas.chat import ChatRequest, ChatSessionRecord, ChatToolTraceItem
from knoarbor.services.chat_evidence import ChatEvidencePlanner

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


@dataclass(frozen=True)
class ChatToolContext:
    request: ChatRequest
    services: ApplicationServices
    existing_session: ChatSessionRecord | None
    evidence_planner: ChatEvidencePlanner
    query_wiki: Callable[[dict[str, Any]], ChatToolTraceItem]
