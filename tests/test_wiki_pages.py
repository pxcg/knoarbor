from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knoarbor.core.schemas.raw_evidence import OriginalSourceRecord, SourceProcessingRecord, SourceUnitRecord
from knoarbor.core.schemas.source_record import SourceRecordAttachment
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.services.wiki_pages import WikiPageService, _raw_markdown_from_source_document
from knoarbor.storage.source_records import read_raw_evidence_records, read_source_processing_records
from tests.transactional_ingest_helpers import publish_record


class WikiPageServiceTests(unittest.TestCase):
    def test_raw_markdown_maps_retained_obsidian_image_without_rewriting_wiki_links(self) -> None:
        document = SourceDocument(
            source_id="markdown:images",
            source_type="markdown",
            origin=SourceOrigin(connector="markdown", uri="file:///paper.md", raw_path="/paper.md"),
            content=SourceContent(
                format="markdown",
                text="# Paper\n\n![[image 15.png]]\n\n![Diagram](assets/diagram.png)\n\n[[Related Page]]\n\n![[missing.png]]",
                attachments=[
                    {
                        "attachment_type": "image",
                        "name": "image 15.png",
                        "relative_path": "raw/derived/assets/images/content-hash.png",
                        "metadata": {"obsidian_target": "image 15.png"},
                    },
                    {
                        "attachment_type": "image",
                        "name": "diagram.png",
                        "relative_path": "raw/derived/assets/images/diagram-hash.png",
                        "metadata": {"markdown_target": "assets/diagram.png"},
                    }
                ],
            ),
            fingerprint=SourceFingerprint(content_hash="hash", connector_version="markdown@1"),
        )

        rendered = _raw_markdown_from_source_document(document)

        self.assertIn("![image 15.png](raw/derived/assets/images/content-hash.png)", rendered or "")
        self.assertIn("![Diagram](raw/derived/assets/images/diagram-hash.png)", rendered or "")
        self.assertIn("[[Related Page]]", rendered or "")
        self.assertIn("![[missing.png]]", rendered or "")

    def test_raw_markdown_does_not_use_attachment_name_as_reference_authority(self) -> None:
        document = SourceDocument(
            source_id="markdown:sidecar",
            source_type="markdown",
            origin=SourceOrigin(connector="markdown", uri="file:///paper.md", raw_path="/paper.md"),
            content=SourceContent(
                format="markdown",
                text="![[missing.png]]",
                attachments=[
                    {
                        "attachment_type": "image",
                        "name": "missing.png",
                        "relative_path": "raw/derived/assets/images/sidecar-hash.png",
                        "metadata": {},
                    }
                ],
            ),
            fingerprint=SourceFingerprint(content_hash="hash", connector_version="markdown@1"),
        )

        rendered = _raw_markdown_from_source_document(document)

        self.assertEqual(rendered, "![[missing.png]]\n")

    def test_projection_page_defaults_to_normalized_raw_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            page_path = vault / "wiki" / "pages" / "Memory--abc123.md"
            page_path.parent.mkdir(parents=True)
            page_path.write_text(
                """---
schema_version: wiki_projection.v1
role: knowledge_page
projection_kind: source_index
not_fact_material: true
raw_record_id: raw:memory
raw_revision_id: rawrev:memory
source_record_id: sr_memory
processing_record_id: spr_memory
---

# Memory

## Synthesis

Locator text.

## Claims

- C1: Memory uses source units.
""",
                encoding="utf-8",
            )
            publish_record(vault, _processing_record())

            detail = WikiPageService().read_page(vault, "Memory--abc123.md")

        self.assertEqual(detail.default_view, "raw")
        self.assertEqual(detail.raw_record_id, "raw:memory")
        self.assertEqual(detail.processing_record_id, "spr_memory")
        self.assertEqual(detail.source_unit_count, 2)
        self.assertEqual(detail.original_source_path, "raw/inbox/notes/memory.md")
        self.assertIsNotNone(detail.raw_content)
        self.assertIn("Raw unit one.", detail.raw_content or "")
        self.assertIn("Raw unit two.", detail.raw_content or "")
        self.assertEqual((detail.raw_content or "").count("Raw unit one."), 1)
        self.assertIn("## Synthesis", detail.wiki_content or "")

    def test_source_revision_replaces_previous_raw_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)

            publish_record(vault, _processing_record(processing_record_id="spr_old", raw_revision_id="rawrev:old", unit_text="Old raw unit."))
            publish_record(vault, _processing_record(processing_record_id="spr_new", raw_revision_id="rawrev:new", unit_text="New raw unit."))

            processing_records = read_source_processing_records(vault)
            evidence_records = read_raw_evidence_records(vault)

            self.assertEqual([record.processing_record_id for record in processing_records], ["spr_new"])
            self.assertEqual([record.raw_revision_id for record in evidence_records], ["rawrev:new"])
            self.assertEqual([record.content for record in evidence_records], ["New raw unit."])

    def test_delete_projection_purges_owned_source_and_does_not_rematerialize_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            page_path = vault / "wiki" / "pages" / "Memory--abc123.md"
            page_path.parent.mkdir(parents=True)
            page_path.write_text(
                """---
schema_version: wiki_projection.v1
role: knowledge_page
raw_record_id: raw:memory
processing_record_id: spr_memory
---

# Memory
""",
                encoding="utf-8",
            )
            image = vault / "raw" / "derived" / "assets" / "images" / "memory.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"memory")
            publish_record(
                vault,
                _processing_record(
                    attachments=[
                        SourceRecordAttachment(
                            attachment_type="image",
                            name="memory.png",
                            relative_path="raw/derived/assets/images/memory.png",
                        )
                    ]
                ),
            )

            result = WikiPageService().delete_page(vault, "Memory--abc123.md")

            self.assertTrue(result.deleted)
            self.assertFalse(page_path.exists())
            self.assertEqual(read_source_processing_records(vault), [])
            self.assertEqual(read_raw_evidence_records(vault), [])
            self.assertEqual(WikiPageService().list_pages(vault).pages, [])
            facts_root = vault / ".knoarbor" / "facts"
            self.assertFalse(facts_root.exists() and any(facts_root.rglob("source.json")))
            self.assertFalse(image.exists())

            publish_record(vault, _processing_record())
            self.assertEqual([record.raw_record_id for record in read_source_processing_records(vault)], ["raw:memory"])


def _processing_record(
    *,
    processing_record_id: str = "spr_memory",
    raw_revision_id: str = "rawrev:memory",
    unit_text: str | None = None,
    attachments: list[SourceRecordAttachment] | None = None,
) -> SourceProcessingRecord:
    unit_texts = [unit_text] if unit_text is not None else ["Raw unit one.", "Raw unit two."]
    return SourceProcessingRecord(
        processing_record_id=processing_record_id,
        raw_record_id="raw:memory",
        raw_revision_id=raw_revision_id,
        source_record_id="sr_memory",
        ingest_profile="auto",
        source=OriginalSourceRecord(
            raw_record_id="raw:memory",
            raw_revision_id=raw_revision_id,
            source_id="markdown:memory",
            source_type="markdown",
            connector="markdown",
            raw_path="raw/inbox/notes/memory.md",
            title="Memory",
            content_hash="hash-original",
            normalized_content_hash="hash-normalized",
        ),
        source_units=[
            SourceUnitRecord(
                source_unit_id=f"unit:{index + 1}",
                raw_record_id="raw:memory",
                raw_revision_id=raw_revision_id,
                unit_index=index,
                unit_type="section",
                title="Design Notes",
                content=text,
                excerpt=text,
                source_path="raw/inbox/notes/memory.md",
            )
            for index, text in enumerate(unit_texts)
        ],
        attachments=attachments or [],
        page_paths=["Memory--abc123.md"],
    )


if __name__ == "__main__":
    unittest.main()
