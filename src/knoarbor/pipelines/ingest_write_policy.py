from __future__ import annotations

from dataclasses import dataclass, field

from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteItem


@dataclass(frozen=True)
class IngestWritePolicyResult:
    items: list[WikiDraftBatchWriteItem]
    changes: list[str] = field(default_factory=list)


class IngestWritePolicy:
    """Validates source-level ingest writes before they reach the vault."""

    def apply(self, items: list[WikiDraftBatchWriteItem]) -> IngestWritePolicyResult:
        source_creates = [
            item
            for item in items
            if item.write_action == "create" and item.wiki_draft.page_dir == "sources"
        ]
        if len(source_creates) <= 1:
            return IngestWritePolicyResult(items=list(items))

        titles = ", ".join(item.wiki_draft.title for item in source_creates)
        raise ValueError(
            "Ingest page planning produced multiple source digest creates for one source; "
            f"expected one source-level source digest. Drafts: {titles}"
        )
