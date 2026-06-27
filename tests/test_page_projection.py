from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_atoms import KnowledgeEvidenceSpan
from knoarbor.core.schemas.knowledge_extract import KnowledgeSource
from knoarbor.core.schemas.source_digest import SourceDigest, SourceDigestUnit
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan
from knoarbor.semantic.page_projection import project_draft_batch_from_page_assembly


class PageProjectionTests(unittest.TestCase):
    def test_source_digest_draft_uses_deterministic_source_units(self) -> None:
        digest = SourceDigest(
            digest_id="sd_memory",
            source=KnowledgeSource(
                source_type="markdown",
                source_app="markdown",
                source_id="markdown:memory",
                source_path="raw/inbox/notes/Memory.md",
                title="Memory",
            ),
            raw_source="raw/inbox/notes/Memory.md",
            content_hash="abc",
            source_focus="Memory strategies",
            summary="Conversation memory note.",
            units=[
                SourceDigestUnit(
                    index=0,
                    unit_type="note",
                    title="Memory",
                    summary="Full history | sliding window strategies.",
                    evidence=KnowledgeEvidenceSpan(
                        source_digest_id="sd_memory",
                        source_path="raw/inbox/notes/Memory.md",
                        source_unit_index=0,
                        excerpt="Full history and sliding window strategies.",
                    ),
                )
            ],
        )
        batch = WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action="create",
                    source_file="raw/inbox/notes/Memory.md",
                    title="Memory Source",
                    page_dir="sources",
                    question="Memory Source",
                    summary="Model summary.",
                    evidence=["bad model row"],
                    synthesis="Source audit.",
                )
            ],
            batch_summary="One source page.",
        )
        plan = WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action="create",
                    page_dir="sources",
                    title="Memory Source",
                    knowledge_object="Memory Source",
                    source_digest_ids=["sd_memory"],
                    decision_reason="Create source page.",
                )
            ],
            overall_summary="Create source page.",
        )

        projected = project_draft_batch_from_page_assembly(batch, {"operations": []}, plan, digest)

        draft = projected.drafts[0]
        self.assertEqual(draft.source_digest_ids, ["sd_memory"])
        self.assertEqual(draft.summary, "Conversation memory note.")
        self.assertEqual(draft.evidence, ["U1 | raw/inbox/notes/Memory.md | unit:0 | Full history / sliding window strategies. | high"])


if __name__ == "__main__":
    unittest.main()
