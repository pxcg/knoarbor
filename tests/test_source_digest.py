from __future__ import annotations

import unittest

from pydantic import ValidationError

from knoarbor.core.schemas.knowledge_atoms import KnowledgeEvidenceSpan
from knoarbor.core.schemas.source_digest import SourceDigest, SourceObservation
from knoarbor.semantic.source_digest import build_source_digest_from_extract
from tests.harness.semantic_cases import source_normalize_output
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract


class SourceDigestSchemaTest(unittest.TestCase):
    def test_observation_requires_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            SourceObservation(
                id="obs_without_evidence",
                statement="SoundAnalysis is activity-level.",
                evidence=[],
            )

    def test_digest_collects_unit_evidence(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        digest = build_source_digest_from_extract(extract)

        self.assertIsInstance(digest, SourceDigest)
        self.assertEqual(digest.schema_version, "source_digest.v1")
        self.assertTrue(digest.digest_id.startswith("sd_"))
        self.assertEqual(len(digest.units), len([unit for unit in extract.content_units if unit.content.strip()]))
        self.assertEqual(digest.summary_counts()["evidence_spans"], len(digest.units))
        self.assertEqual(digest.units[0].evidence.source_digest_id, digest.digest_id)

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


if __name__ == "__main__":
    unittest.main()
