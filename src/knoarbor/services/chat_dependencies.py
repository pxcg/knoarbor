from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from knoarbor.services.chat_agent import ChatAgentService
    from knoarbor.services.chat_knowledge_tools import ChatKnowledgeService
    from knoarbor.services.chat_sessions import ChatSessionStore
    from knoarbor.services.image_generation import ImageGenerationService
    from knoarbor.services.ingest_coordinator import IngestCoordinator
    from knoarbor.services.memory import MemoryService
    from knoarbor.services.vault_registry import VaultRegistryService


class ChatMemoryDependencies(Protocol):
    memory: MemoryService


class ChatSessionDependencies(Protocol):
    chat_sessions: ChatSessionStore


class ChatToolDependencies(Protocol):
    chat_knowledge: ChatKnowledgeService
    image_generation: ImageGenerationService
    vaults: VaultRegistryService


class ChatAgentDependencies(
    ChatMemoryDependencies,
    ChatSessionDependencies,
    ChatToolDependencies,
    Protocol,
):
    """Capabilities required to execute and persist one chat request."""


class ChatExecutionDependencies(ChatAgentDependencies, Protocol):
    chat: ChatAgentService


class ChatWorkflowDependencies(ChatExecutionDependencies, Protocol):
    ingest_coordinator: IngestCoordinator
