from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knoarbor.core.schemas.chat import ChatMessageItem, ChatRequest
from knoarbor.core.schemas.raw_evidence import (
    OriginalSourceRecord,
    SourceProcessingRecord,
    SourceUnitRecord,
)
from knoarbor.core.schemas.source_record import SourceRecordAttachment
from knoarbor.pipelines.query_batch import BM25_GLOBAL_RESULT_WINDOW
from knoarbor.retrieval.evidence_selection import (
    EvidenceSelectionCandidate,
    explain_structural_evidence,
    select_structural_evidence,
)
from knoarbor.services import ApplicationServices
from knoarbor.services.chat_knowledge_tools import _retrieve_knowledge_batch
from knoarbor.services.chat_support_spans import build_support_spans
from knoarbor.services.chat_tool_context import ChatToolContext
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.source_revisions import read_active_processing_records
from tests.test_semantic_indexed_query import _batch, _record, _relation_batch
from tests.transactional_ingest_helpers import publish_batch, publish_record


class _Signal:
    def __init__(
        self,
        channel: str,
        *spans: tuple[int, int],
    ) -> None:
        self.channel = channel
        self.matched_spans = spans


class _Handle:
    def __init__(self, *signals: _Signal) -> None:
        self.signals = signals


class ChatKnowledgeToolsTest(unittest.TestCase):
    def test_answer_attachment_metadata_reads_each_vault_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for index in range(2):
                publish_record(
                    vault,
                    _record(
                        f"shared-{index}",
                        f"Shared attachment metadata evidence {index}.",
                    ),
                )
            VaultMaterializer().reconcile(vault, force=True)

            with patch(
                "knoarbor.services.chat_knowledge_tools."
                "read_active_processing_records",
                wraps=read_active_processing_records,
            ) as read_records:
                result = _retrieve_knowledge_batch(
                    _context(vault, "shared attachment metadata"),
                    {
                        "query_expressions": [
                            {
                                "query_id": "q1",
                                "query": "shared attachment metadata",
                            }
                        ],
                    },
                )

        self.assertGreaterEqual(result.result["evidence_count"], 2)
        self.assertEqual(read_records.call_count, 1)

    def test_structural_selection_uses_exact_spans_not_relevance_scores(
        self,
    ) -> None:
        candidates = (
            EvidenceSelectionCandidate(
                key="claim",
                handle=_Handle(_Signal("atom_claim", (10, 20))),
                query_ids=("q1",),
            ),
            EvidenceSelectionCandidate(
                key="raw",
                handle=_Handle(_Signal("raw_lexical", (30, 40))),
                query_ids=("q1",),
            ),
            EvidenceSelectionCandidate(
                key="no-span",
                handle=_Handle(_Signal("atom_claim")),
                query_ids=("q1",),
            ),
        )

        selected = select_structural_evidence(candidates)
        explained = explain_structural_evidence(candidates)

        self.assertEqual([item.key for item in selected], ["claim", "raw"])
        self.assertTrue(
            selected[0].reasons[0].startswith(
                "structural_evidence.v1:decision=selected"
            )
        )
        self.assertEqual(
            explained["no-span"],
            (
                "structural_evidence.v1:"
                "decision=rejected:reason=no_exact_span",
            ),
        )

    def test_chat_receives_query_selected_exact_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            VaultMaterializer().reconcile(vault, force=True)
            result = _retrieve_knowledge_batch(
                _context(vault, "dynamic tool decisions"),
                {
                    "query_expressions": [
                        {
                            "query_id": "q1",
                            "query": "dynamic tool decisions",
                        }
                    ],
                },
            )

        self.assertEqual(
            result.result["selected_evidence_ids"],
            [item["evidence_id"] for item in result.result["raw_evidence"]],
        )
        self.assertEqual(
            result.result["raw_read_count"],
            result.result["evidence_count"],
        )
        self.assertEqual(
            result.result["global_result_window"],
            BM25_GLOBAL_RESULT_WINDOW,
        )
        self.assertGreaterEqual(
            result.result["global_eligible_candidate_count"],
            result.result["candidate_count"],
        )
        self.assertTrue(result.result["evidence_selection_reasons"])
        for item in result.result["raw_evidence"]:
            self.assertTrue(item["evidence_segments"])
            self.assertEqual(
                item["content"],
                "\n\n".join(
                    segment["text"]
                    for segment in item["evidence_segments"]
                ),
            )

    def test_support_spans_preserve_disjoint_segment_offsets(self) -> None:
        item = {
            "evidence_id": "ev:segments",
            "source_unit_id": "unit:segments",
            "evidence_segments": [
                {
                    "text": "First requested fact.",
                    "char_start": 100,
                    "char_end": 121,
                },
                {
                    "text": "Second requested fact.",
                    "char_start": 300,
                    "char_end": 322,
                },
            ],
        }

        spans = build_support_spans(item, evidence_index=0)

        self.assertEqual(
            [(span.text, span.char_start, span.char_end) for span in spans],
            [
                ("First requested fact.", 100, 121),
                ("Second requested fact.", 300, 322),
            ],
        )

    def test_selected_raw_retains_ingested_image_attachments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            image = (
                vault
                / "raw"
                / "derived"
                / "assets"
                / "images"
                / "figure.png"
            )
            image.parent.mkdir(parents=True)
            image.write_bytes(b"image")
            content = (
                "Diagram evidence explains the ingest flow.\n\n"
                "![Ingest flow](images/figure.png)"
            )
            record = SourceProcessingRecord(
                processing_record_id="spr:image",
                raw_record_id="raw:image",
                raw_revision_id="rawrev:image",
                source_record_id="source:image",
                source=OriginalSourceRecord(
                    raw_record_id="raw:image",
                    raw_revision_id="rawrev:image",
                    source_id="source:image",
                    raw_path="raw/image.md",
                ),
                source_units=[
                    SourceUnitRecord(
                        source_unit_id="unit:image",
                        raw_record_id="raw:image",
                        raw_revision_id="rawrev:image",
                        unit_index=0,
                        content=content,
                        excerpt=content,
                        source_path="raw/image.md",
                    )
                ],
                attachments=[
                    SourceRecordAttachment(
                        attachment_id="attachment:figure",
                        attachment_type="image",
                        name="figure.png",
                        topic="Ingest flow",
                        relative_path="images/figure.png",
                        mime_type="image/png",
                        status="used",
                    ),
                    SourceRecordAttachment(
                        attachment_id="attachment:unrelated",
                        attachment_type="image",
                        name="unrelated.png",
                        topic="Unrelated figure",
                        relative_path="images/unrelated.png",
                        mime_type="image/png",
                        status="candidate",
                    ),
                ],
            )
            publish_record(vault, record)
            VaultMaterializer().reconcile(vault, force=True)
            result = _retrieve_knowledge_batch(
                _context(vault, "diagram ingest flow"),
                {
                    "query_expressions": [
                        {
                            "query_id": "q1",
                            "query": "diagram ingest flow",
                        }
                    ],
                },
            )

        attachments = result.result["raw_evidence"][0]["attachments"]
        self.assertEqual(attachments[0]["attachment_id"], "attachment:figure")
        self.assertIn("/vault-assets/", attachments[0]["src"])
        self.assertEqual(len(attachments), 1)
        self.assertNotIn("metadata", attachments[0])

    def test_relation_atom_resolves_its_own_claim_to_complete_raw(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for source_id, unit_id, claim_id, text, subject, predicate, obj in (
                (
                    "source:alpha",
                    "unit:alpha",
                    "claim:alpha",
                    "Alpha routes ZXQ9917 telemetry to Bridge.",
                    ("ent:alpha", "Alpha"),
                    "routes ZXQ9917 telemetry to",
                    ("ent:bridge", "Bridge"),
                ),
                (
                    "source:bridge",
                    "unit:bridge",
                    "claim:bridge",
                    "Bridge forwards telemetry to Gamma.",
                    ("ent:bridge", "Bridge"),
                    "forwards telemetry to",
                    ("ent:gamma", "Gamma"),
                ),
            ):
                publish_record(
                    vault,
                    _record(
                        source_id.removeprefix("source:"),
                        text,
                        source_unit_id=unit_id,
                    ),
                    _relation_batch(
                        source_id=source_id,
                        source_unit_id=unit_id,
                        claim_id=claim_id,
                        claim=text,
                        subject=subject,
                        predicate=predicate,
                        obj=obj,
                    ),
                )
            VaultMaterializer().reconcile(vault, force=True)
            result = _retrieve_knowledge_batch(
                _context(vault, "ZXQ9917"),
                {
                    "query_expressions": [
                        {
                            "query_id": "q1",
                            "query": "ZXQ9917",
                        }
                    ],
                },
            )

        self.assertEqual(
            {
                item["source_record_id"]
                for item in result.result["raw_evidence"]
            },
            {"source:alpha"},
        )
        self.assertTrue(
            all(
                reason.startswith("structural_evidence.v1:")
                for reasons in result.result[
                    "evidence_selection_reasons"
                ].values()
                for reason in reasons
            )
        )


def _context(vault: Path, message: str) -> ChatToolContext:
    return ChatToolContext(
        request=ChatRequest(
            vault_path=str(vault),
            message=ChatMessageItem(role="user", content=message),
            append_ledger=False,
        ),
        services=ApplicationServices(),
    )


if __name__ == "__main__":
    unittest.main()
