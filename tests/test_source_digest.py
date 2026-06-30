from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from knoarbor.core.schemas.knowledge_atoms import KnowledgeEvidenceSpan
from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.semantic.source_digest import build_source_digest_from_extract
from knoarbor.semantic.source_digest_drafts import build_source_digest_write_item
from tests.harness.semantic_cases import source_normalize_output
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract


class SourceDigestSchemaTest(unittest.TestCase):
    def test_digest_collects_unit_evidence(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        digest = build_source_digest_from_extract(extract)

        self.assertIsInstance(digest, SourceDigest)
        self.assertEqual(digest.schema_version, "source_digest.v1")
        self.assertTrue(digest.digest_id.startswith("sd_"))
        self.assertEqual(len(digest.units), len([unit for unit in extract.content_units if unit.content.strip()]))
        self.assertEqual(digest.summary_counts()["evidence_spans"], len(digest.units))
        self.assertEqual(digest.units[0].evidence.source_digest_id, digest.digest_id)
        self.assertEqual(digest.raw_source, extract.source.source_path)
        self.assertIsNotNone(digest.content_hash)
        self.assertEqual(digest.summary_counts()["contributions"], 0)
        self.assertEqual(digest.summary_counts()["unresolved"], len(digest.unresolved_items))

    def test_digest_preserves_existing_evidence_without_duplicates(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        span = KnowledgeEvidenceSpan(
            source_digest_id="custom_digest",
            source_unit_index=99,
            excerpt="external evidence",
            excerpt_hash="external",
        )
        digest = build_source_digest_from_extract(extract, digest_id="custom_digest")
        copied = digest.model_copy(update={"evidence_spans": [span]})
        validated = SourceDigest.model_validate(copied.model_dump())

        self.assertEqual(validated.evidence_spans[0].excerpt, "external evidence")
        self.assertGreaterEqual(validated.summary_counts()["evidence_spans"], 1)

    def test_digest_projects_extract_warnings_to_unresolved_items(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        extract.warnings.append("Low confidence source unit.")

        digest = build_source_digest_from_extract(extract)

        self.assertEqual(digest.unresolved_items[0].item_type, "warning")
        self.assertEqual(digest.unresolved_items[0].reason, "Low confidence source unit.")
        self.assertEqual(digest.unresolved_items[0].evidence_unit_ids, ["U1"])

    def test_digest_preserves_source_attachments(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        extract.attachments.append(
            {
                "attachment_type": "image",
                "name": "figure-1.png",
                "description": "System architecture figure.",
                "relative_path": "images/figure-1.png",
                "mime_type": "image/png",
                "content_hash": "abc123",
                "source": "mineru",
                "metadata": {"image_caption": ["Agent loop diagram"], "sub_type": "flowchart", "page_idx": 2, "bbox": [1, 2, 3, 4]},
            }
        )

        digest = build_source_digest_from_extract(extract)

        self.assertEqual(digest.summary_counts()["attachments"], 1)
        self.assertEqual(digest.attachments[0].name, "figure-1.png")
        self.assertEqual(digest.attachments[0].attachment_id, "A1")
        self.assertEqual(digest.attachments[0].topic, "Agent loop diagram")
        self.assertEqual(digest.attachments[0].relative_path, "images/figure-1.png")
        self.assertEqual(digest.attachments[0].source_range, "page_idx:2 bbox:1,2,3,4")
        self.assertEqual(digest.attachments[0].status, "candidate")

    def test_digest_dedupes_attachments_by_stable_identity(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        extract.attachments.extend(
            [
                {
                    "attachment_type": "image",
                    "name": "ac1-abcdef1234567890abcdef1234567890.jpg",
                    "description": "AC1 front rendering.",
                    "relative_path": "images/ac1.jpg",
                    "content_hash": "same-hash",
                    "metadata": {"caption": "图1 AC1 外观图"},
                },
                {
                    "attachment_type": "image",
                    "name": "ac1-copy.jpg",
                    "description": "Duplicate path from Markdown scan.",
                    "relative_path": "images/ac1.jpg",
                    "content_hash": "same-hash",
                    "metadata": {"caption": "图1 AC1 外观图"},
                },
            ]
        )

        digest = build_source_digest_from_extract(extract)

        self.assertEqual(digest.summary_counts()["attachments"], 1)
        self.assertEqual(digest.attachments[0].topic, "图1 AC1 外观图")
        self.assertEqual(digest.attachments[0].description, "AC1 front rendering.")

    def test_source_digest_write_item_resolves_existing_audit_page(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        extract.attachments.append(
            {
                "attachment_type": "image",
                "name": "figure-1.png",
                "description": "System architecture figure.",
                "relative_path": "images/figure-1.png",
                "metadata": {"image_caption": ["Agent loop diagram"], "page_idx": 2},
            }
        )
        digest = build_source_digest_from_extract(extract)

        with TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            source_dir = vault / "wiki" / "sources"
            source_dir.mkdir(parents=True)
            (source_dir / "Agent-Source-Digest.md").write_text(
                "---\n"
                "source: raw/notes/Agent.md\n"
                "content_hash: old\n"
                "---\n\n"
                "# Agent Source Digest\n\n## Raw Source\n\nraw/notes/Agent.md\n",
                encoding="utf-8",
            )
            write_item = build_source_digest_write_item(
                vault_path=vault,
                source_digest=digest,
                source_file="raw/notes/Agent.md",
                display_source_file="raw/notes/Agent.md",
            )

        self.assertEqual(write_item.write_action, "update")
        self.assertEqual(write_item.target_page, "sources/Agent-Source-Digest.md")
        self.assertEqual(write_item.wiki_draft.page_dir, "sources")
        self.assertEqual(write_item.wiki_draft.attachments[0]["topic"], "Agent loop diagram")
        self.assertEqual(write_item.wiki_draft.attachments[0]["description"], "System architecture figure.")


if __name__ == "__main__":
    unittest.main()
