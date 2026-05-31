from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.redaction import redact_source_document
from knoarbor.core.schemas.sources import (
    SourceContent,
    SourceDocument,
    SourceFingerprint,
    SourceOrigin,
)


def make_document(text: str) -> SourceDocument:
    return SourceDocument(
        source_id="note-1",
        source_type="markdown",
        origin=SourceOrigin(
            connector="markdown",
            uri="file:///Users/alice/notes/private.md",
            raw_path="raw/notes/private.md",
        ),
        content=SourceContent(
            format="markdown",
            text=text,
            sections=[{"heading": "Contact", "text": "owner alice@example.com"}],
            attachments=[{"path": "/Users/alice/Desktop/image.png"}],
        ),
        metadata={"title": "Private note", "local_path": "/Users/alice/notes/private.md"},
        fingerprint=SourceFingerprint(content_hash="abc123", connector_version="test"),
    )


class RedactionTests(unittest.TestCase):
    def test_redacts_sensitive_text_before_model_input(self) -> None:
        document = make_document(
            "\n".join(
                [
                    "Email alice@example.com",
                    "Phone 13800138000",
                    "DEEPSEEK_API_KEY=sk-1234567890abcdefghijklmnop",
                    "Token sk-abcdefghijklmnop1234567890",
                    "Path /Users/alice/Projects/KnoArbor",
                    "-----BEGIN PRIVATE KEY-----secret-----END PRIVATE KEY-----",
                ]
            )
        )

        result = redact_source_document(document, PrivacyConfig())

        self.assertTrue(result.enabled)
        payload = result.document.model_dump_json()
        self.assertNotIn("alice@example.com", payload)
        self.assertNotIn("13800138000", payload)
        self.assertNotIn("sk-1234567890abcdefghijklmnop", payload)
        self.assertNotIn("sk-abcdefghijklmnop1234567890", payload)
        self.assertNotIn("/Users/alice", payload)
        self.assertNotIn("PRIVATE KEY-----secret", payload)
        self.assertGreaterEqual(result.counts["emails"], 2)
        self.assertEqual(result.counts["phone_numbers"], 1)
        self.assertEqual(result.counts["api_keys"], 1)
        self.assertEqual(result.counts["env_secrets"], 1)
        self.assertEqual(result.document.metadata["redaction"]["enabled"], True)

    def test_can_disable_redaction(self) -> None:
        document = make_document("Email alice@example.com")

        result = redact_source_document(document, PrivacyConfig(redaction_enabled=False))

        self.assertFalse(result.enabled)
        self.assertIs(result.document, document)
        self.assertEqual(result.counts, {})


if __name__ == "__main__":
    unittest.main()
