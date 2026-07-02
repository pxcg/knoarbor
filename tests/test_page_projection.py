from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_atoms import KnowledgeEvidenceSpan
from knoarbor.core.schemas.knowledge_extract import KnowledgeSource
from knoarbor.core.schemas.source_digest import SourceDigest, SourceDigestAttachment, SourceDigestUnit
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

        projected = project_draft_batch_from_page_assembly(
            batch,
            {
                "operations": [
                    {
                        "operation_index": 0,
                        "claims": [{"text": "C1. [[AC1]] has a documented exterior diagram."}],
                        "entities": ["[[AC1]]"],
                        "relations": [],
                        "evidence": [{"claim": "C1", "source": "sd_ac1", "range": "unit:0", "basis": "figure evidence", "confidence": "high"}],
                        "source_digest_ids": ["sd_ac1"],
                        "atom_ids": ["kc_1"],
                    }
                ]
            },
            plan,
            digest,
        )

        draft = projected.drafts[0]
        self.assertEqual(draft.source_digest_ids, ["sd_memory"])
        self.assertEqual(draft.summary, "Conversation memory note.")
        self.assertEqual(draft.evidence, ["U1 | raw/inbox/notes/Memory.md | unit:0 | Full history / sliding window strategies. | high"])

    def test_wiki_draft_attachment_projection_ignores_generic_model_descriptions(self) -> None:
        digest = SourceDigest(
            digest_id="sd_ac1",
            source=KnowledgeSource(
                source_type="markdown",
                source_app="markdown",
                source_id="markdown:ac1",
                source_path="raw/derived/markdown/AC1中文.md",
                title="AC1中文",
            ),
            raw_source="raw/derived/markdown/AC1中文.md",
            content_hash="abc",
            source_focus="AC1",
            summary="AC1 source.",
            attachments=[
                SourceDigestAttachment(
                    attachment_id="A1",
                    attachment_type="image",
                    name="figure-1.jpg",
                    topic="图1 AC1 外形图",
                    description="Pure diagram of the AC1 housing and connector layout.",
                    relative_path="images/figure-1.jpg",
                    content_hash="hash-1",
                )
            ],
        )
        batch = WikiDraftBatch(
            drafts=[
                WikiDraftBatchItem(
                    operation_index=0,
                    write_action="create",
                    source_file="raw/derived/markdown/AC1中文.md",
                    title="RoboSense AC1",
                    page_dir="pages",
                    question="AC1",
                    summary="AC1 summary.",
                    claims=["C1. [[AC1]] has a documented exterior diagram."],
                    evidence=["C1 | sd_ac1 | unit:0 | figure evidence | high"],
                    synthesis="AC1 synthesis.",
                    attachments=[{"name": "figure-1.jpg", "description": "产品图片"}],
                )
            ],
            batch_summary="One wiki page.",
        )
        plan = WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action="create",
                    page_dir="pages",
                    title="RoboSense AC1",
                    knowledge_object="RoboSense AC1",
                    source_digest_ids=["sd_ac1"],
                    selected_claim_ids=["kc_1"],
                    decision_reason="Create AC1 page.",
                )
            ],
            overall_summary="Create AC1 page.",
        )

        projected = project_draft_batch_from_page_assembly(
            batch,
            {
                "operations": [
                    {
                        "operation_index": 0,
                        "claims": [{"text": "C1. [[AC1]] has a documented exterior diagram."}],
                        "entities": ["[[AC1]]"],
                        "relations": [],
                        "evidence": [{"claim": "C1", "source": "sd_ac1", "range": "unit:0", "basis": "figure evidence", "confidence": "high"}],
                        "source_digest_ids": ["sd_ac1"],
                        "atom_ids": ["kc_1"],
                    }
                ]
            },
            plan,
            digest,
        )

        attachment = projected.drafts[0].attachments[0]
        self.assertEqual(attachment["topic"], "图1 AC1 外形图")
        self.assertEqual(attachment["description"], "Pure diagram of the AC1 housing and connector layout.")


if __name__ == "__main__":
    unittest.main()
