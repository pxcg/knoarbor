from __future__ import annotations

from dataclasses import dataclass, field

from knoarbor.services.chat_agent import ChatAgentService
from knoarbor.services.chat_sessions import ChatSessionStore
from knoarbor.services.doctor import DoctorService
from knoarbor.services.ingest import IngestService
from knoarbor.services.model_probe import ModelProbeService
from knoarbor.services.memory import MemoryService
from knoarbor.services.run_manager import RunManager
from knoarbor.services.source_catalog import SourceCatalogService
from knoarbor.services.vault_registry import VaultRegistryService
from knoarbor.services.wiki_linter import WikiLinterService
from knoarbor.services.wiki_pages import WikiPageService
from knoarbor.services.wiki_reports import WikiReportService
from knoarbor.services.wiki_search import WikiSearchService


@dataclass
class ApplicationServices:
    chat: ChatAgentService = field(default_factory=ChatAgentService)
    chat_sessions: ChatSessionStore = field(default_factory=ChatSessionStore)
    doctor: DoctorService = field(default_factory=DoctorService)
    wiki_linter: WikiLinterService = field(default_factory=WikiLinterService)
    wiki_search: WikiSearchService = field(default_factory=WikiSearchService)
    ingest: IngestService = field(default_factory=IngestService)
    runs: RunManager = field(default_factory=RunManager)
    source_catalog: SourceCatalogService = field(default_factory=SourceCatalogService)
    model_probe: ModelProbeService = field(default_factory=ModelProbeService)
    memory: MemoryService = field(default_factory=MemoryService)
    vaults: VaultRegistryService = field(default_factory=VaultRegistryService)
    wiki_pages: WikiPageService = field(default_factory=WikiPageService)
    wiki_reports: WikiReportService = field(default_factory=WikiReportService)
