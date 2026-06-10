from __future__ import annotations

from dataclasses import dataclass, field

from knoarbor.services.doctor import DoctorService
from knoarbor.services.ingest import IngestService
from knoarbor.services.model_probe import ModelProbeService
from knoarbor.services.run_manager import RunManager
from knoarbor.services.source_catalog import SourceCatalogService
from knoarbor.services.vault_registry import VaultRegistryService
from knoarbor.services.wiki_linter import WikiLinterService
from knoarbor.services.wiki_search import WikiSearchService


@dataclass
class ApplicationServices:
    doctor: DoctorService = field(default_factory=DoctorService)
    wiki_linter: WikiLinterService = field(default_factory=WikiLinterService)
    wiki_search: WikiSearchService = field(default_factory=WikiSearchService)
    ingest: IngestService = field(default_factory=IngestService)
    runs: RunManager = field(default_factory=RunManager)
    source_catalog: SourceCatalogService = field(default_factory=SourceCatalogService)
    model_probe: ModelProbeService = field(default_factory=ModelProbeService)
    vaults: VaultRegistryService = field(default_factory=VaultRegistryService)
