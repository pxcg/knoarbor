from __future__ import annotations

from dataclasses import dataclass, field

from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteItem, WikiDraftInput
from knoarbor.core.wiki_lists import merge_unique_items


@dataclass(frozen=True)
class IngestWritePolicyResult:
    items: list[WikiDraftBatchWriteItem]
    changes: list[str] = field(default_factory=list)


class IngestWritePolicy:
    """Normalizes source-level ingest writes before they reach the vault.

    The semantic workflow may run once per segment for long sources. This
    policy enforces source-level invariants that no single segment can know:
    a raw source should produce at most one source digest in one ingest batch.
    """

    def apply(self, items: list[WikiDraftBatchWriteItem]) -> IngestWritePolicyResult:
        source_creates = [
            item
            for item in items
            if item.write_action == "create" and item.wiki_draft.page_dir == "sources"
        ]
        if len(source_creates) <= 1:
            return IngestWritePolicyResult(items=list(items))

        primary = source_creates[0]
        merged_primary = primary.model_copy(update={"wiki_draft": _merge_source_digests(source_creates)})
        skipped_ids = {id(item) for item in source_creates[1:]}

        normalized: list[WikiDraftBatchWriteItem] = []
        for item in items:
            if id(item) == id(primary):
                normalized.append(merged_primary)
            elif id(item) not in skipped_ids:
                normalized.append(item)

        return IngestWritePolicyResult(
            items=normalized,
            changes=[f"merged_source_digest_creates:{len(source_creates)}->1"],
        )


def _merge_source_digests(items: list[WikiDraftBatchWriteItem]) -> WikiDraftInput:
    drafts = [item.wiki_draft for item in items]
    primary = drafts[0]
    return primary.model_copy(
        update={
            "summary": _join_unique_blocks([draft.summary for draft in drafts], max_blocks=3),
            "answer": _join_unique_blocks([draft.answer for draft in drafts], max_blocks=8),
            "claims": merge_unique_items([claim for draft in drafts for claim in draft.claims], [], 24),
            "entities": merge_unique_items([entity for draft in drafts for entity in draft.entities], [], 48),
            "relations": merge_unique_items([relation for draft in drafts for relation in draft.relations], [], 24),
            "evidence": merge_unique_items([evidence for draft in drafts for evidence in draft.evidence], [], 48),
            "synthesis": _join_unique_blocks([draft.synthesis or draft.answer for draft in drafts], max_blocks=8),
            "key_points": [],
            "tags": [],
            "confidence": min(draft.confidence for draft in drafts),
        }
    )


def _join_unique_blocks(blocks: list[str], *, max_blocks: int) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        text = str(block).strip()
        if not text:
            continue
        key = " ".join(text.lower().split())
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= max_blocks:
            break
    return "\n\n".join(result)
