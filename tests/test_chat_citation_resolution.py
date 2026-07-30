from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from knoarbor.entrypoints.api import create_app
from knoarbor.core.schemas.chat import ChatCitation, ChatCitationSpan
from knoarbor.core.schemas.raw_evidence import (
    OriginalSourceRecord,
    SourceProcessingRecord,
    SourceUnitRecord,
)
from knoarbor.services.chat_citation_resolution import ChatCitationResolutionService


class ChatCitationResolutionTests(unittest.TestCase):
    def test_resolves_answer_span_in_source_unit_coordinate_space(self) -> None:
        unit_text = (
            "Appendix text before the cited statement.\n"
            "Technology advances should be monitored and deployed.\n"
            "Appendix text after the cited statement."
        )
        selected = "Technology advances should be monitored and deployed."
        selected_start = unit_text.index(selected)
        citation = ChatCitation(
            kind="raw_evidence",
            evidence_id="evh:nist",
            raw_revision_id="rawrev:nist",
            source_unit_id="unit:nist-appendix",
            char_start=selected_start,
            char_end=selected_start + len(selected),
        )

        with patch(
            "knoarbor.services.chat_citation_resolution.read_source_processing_records",
            return_value=[_record(unit_text)],
        ):
            response = ChatCitationResolutionService().resolve(Path("/vault"), [citation])

        self.assertEqual(response.resolutions[0].status, "resolved")
        self.assertEqual(response.resolutions[0].text, selected)
        self.assertEqual(response.resolutions[0].texts, [selected])

    def test_resolves_all_exact_ranges_for_one_public_raw_citation(self) -> None:
        unit_text = "First support. Unused middle. Final support."
        first = "First support."
        final = "Final support."
        citation = ChatCitation(
            kind="raw_evidence",
            evidence_id="evh:nist",
            raw_revision_id="rawrev:nist",
            source_unit_id="unit:nist-appendix",
            char_start=0,
            char_end=len(first),
            spans=[
                ChatCitationSpan(char_start=0, char_end=len(first)),
                ChatCitationSpan(
                    char_start=unit_text.index(final),
                    char_end=unit_text.index(final) + len(final),
                ),
            ],
        )

        with patch(
            "knoarbor.services.chat_citation_resolution.read_source_processing_records",
            return_value=[_record(unit_text)],
        ):
            response = ChatCitationResolutionService().resolve(
                Path("/vault"),
                [citation],
            )

        self.assertEqual(response.resolutions[0].status, "resolved")
        self.assertEqual(response.resolutions[0].text, first)
        self.assertEqual(response.resolutions[0].texts, [first, final])

    def test_rejects_span_outside_its_source_unit_instead_of_guessing(self) -> None:
        citation = ChatCitation(
            kind="raw_evidence",
            evidence_id="evh:nist",
            raw_revision_id="rawrev:nist",
            source_unit_id="unit:nist-appendix",
            char_start=500,
            char_end=550,
        )

        with patch(
            "knoarbor.services.chat_citation_resolution.read_source_processing_records",
            return_value=[_record("Short source unit.")],
        ):
            response = ChatCitationResolutionService().resolve(Path("/vault"), [citation])

        self.assertEqual(response.resolutions[0].status, "unavailable")
        self.assertIsNone(response.resolutions[0].text)

    def test_resolution_does_not_add_excerpt_to_persisted_citation(self) -> None:
        citation = ChatCitation(
            kind="raw_evidence",
            raw_revision_id="rawrev:nist",
            source_unit_id="unit:nist-appendix",
            char_start=0,
            char_end=5,
        )

        self.assertNotIn("excerpt", citation.model_dump())

    def test_api_returns_transient_resolution_without_mutating_citation(self) -> None:
        content = "Technology advances should be monitored."
        citation = {
            "kind": "raw_evidence",
            "raw_revision_id": "rawrev:nist",
            "source_unit_id": "unit:nist-appendix",
            "char_start": 0,
            "char_end": len(content),
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            vault.mkdir()
            config = root / "config.yaml"
            config.write_text(
                f"vault:\n  path: {vault}\n",
                encoding="utf-8",
            )
            with patch(
                "knoarbor.services.chat_citation_resolution.read_source_processing_records",
                return_value=[_record(content)],
            ):
                response = TestClient(create_app()).post(
                    "/chat/citations/resolve",
                    json={
                        "config_path": str(config),
                        "citations": [citation],
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "schema_version": "chat_citation_resolve_response.v1",
                "resolutions": [
                    {
                        "index": 0,
                        "status": "resolved",
                        "text": content,
                        "texts": [content],
                    }
                ],
            },
        )
        self.assertNotIn("excerpt", citation)


def _record(content: str) -> SourceProcessingRecord:
    unit = SourceUnitRecord(
        source_unit_id="unit:nist-appendix",
        raw_record_id="raw:nist",
        raw_revision_id="rawrev:nist",
        unit_index=4,
        unit_type="section",
        title="Appendix B",
        content=content,
        excerpt=content,
        excerpt_hash="hash",
        char_start=0,
        char_end=len(content),
        source_path="raw/derived/markdown/nist.md",
    )
    return SourceProcessingRecord(
        processing_record_id="spr:nist",
        raw_record_id="raw:nist",
        raw_revision_id="rawrev:nist",
        source_record_id="source:nist",
        source=OriginalSourceRecord(
            raw_record_id="raw:nist",
            raw_revision_id="rawrev:nist",
            source_id="nist",
            raw_path="raw/derived/markdown/nist.md",
        ),
        source_units=[unit],
        page_paths=["nist.md"],
    )


if __name__ == "__main__":
    unittest.main()
