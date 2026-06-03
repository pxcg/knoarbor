from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.schemas.wiki_operation import WikiOperationApplyRequest, WikiOperationApplyResponse
from knoarbor.maintenance import apply_wiki_operation
from knoarbor.runtime import runtime_logger, vault_write_lock


logger = runtime_logger(__name__)


class WikiOperationPipeline:
    """Applies reviewed wiki maintenance operations and writes the ledger."""

    def __init__(self, *, privacy_config: PrivacyConfig | None = None) -> None:
        self.privacy_config = privacy_config or PrivacyConfig()

    def apply(self, request: WikiOperationApplyRequest) -> WikiOperationApplyResponse:
        vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
        with vault_write_lock(vault_path):
            logger.info("wiki_operations_started operations=%s vault=%s", len(request.operations), vault_path)
            results = [
                apply_wiki_operation(vault_path, operation, request.ledger_path, privacy_config=self.privacy_config)
                for operation in request.operations
            ]
            logger.info("wiki_operations_finished applied=%s vault=%s", len(results), vault_path)
        return WikiOperationApplyResponse(
            results=results,
            stats={
                "applied_count": len(results),
                "operation_ids": [result.operation_id for result in results],
                "actions": [result.action for result in results],
            },
        )
