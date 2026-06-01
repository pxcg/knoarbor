from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from knoarbor.core.schemas.ingest_run import IngestRecoveryRunRequest, UnifiedIngestRequest
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.core.schemas.wiki_query import WikiSearchRequest

RunStartFlow = Literal["ingest", "lint", "query"]


class RunStartRequest(BaseModel):
    """Public run queue request facade.

    `flow` selects the workflow, while the matching nested payload carries the
    workflow-specific contract. Ingest recovery is represented as an ingest run
    with `recovery_of_run_id`, so the public API does not need a separate
    recovery path.
    """

    flow: RunStartFlow
    ingest: UnifiedIngestRequest | None = None
    lint: LintRunRequest | None = None
    query: WikiSearchRequest | None = None
    recovery_of_run_id: str | None = None
    recovery: IngestRecoveryRunRequest | None = None
    vault_path: str | None = None

    @model_validator(mode="after")
    def validate_flow_payload(self) -> "RunStartRequest":
        if self.flow == "ingest" and self.ingest is None and self.recovery_of_run_id is None:
            raise ValueError("ingest payload or recovery_of_run_id is required when flow='ingest'.")
        if self.flow == "lint" and self.lint is None:
            raise ValueError("lint payload is required when flow='lint'.")
        if self.flow == "query" and self.query is None:
            raise ValueError("query payload is required when flow='query'.")
        if self.recovery_of_run_id and not self.vault_path:
            raise ValueError("vault_path is required for ingest recovery runs.")
        return self
