from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.redaction import detect_sensitive_text, redact_public_text, redact_source_document
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
            raw_path="raw/inbox/notes/private.md",
        ),
        content=SourceContent(
            format="markdown",
            text=text,
            sections=[{"heading": "Contact", "text": "owner alice@example.com"}],
            attachments=[
                {
                    "name": "11602df6040f9fef74f63e0f44eadfe2f3ec4f14967004112cd292b1e583783f.jpg",
                    "path": "/Users/alice/Desktop/image.png",
                    "relative_path": (
                        "raw/derived/assets/images/"
                        "11602df6040f9fef74f63e0f44eadfe2f3ec4f14967004112cd292b1e583783f.jpg"
                    ),
                    "content_hash": "11602df6040f9fef74f63e0f44eadfe2f3ec4f14967004112cd292b1e583783f",
                    "description": "Call 13800138000 for the figure.",
                }
            ],
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
                    "MODEL_API_KEY=sk-1234567890abcdefghijklmnop",
                    "Token sk-abcdefghijklmnop1234567890",
                    "Feishu app cli_aa9f1cd454399bc8",
                    "Path /Users/alice/Projects/KnoArbor",
                    "-----BEGIN PRIVATE KEY-----secret-----END PRIVATE KEY-----",
                ]
            )
        )

        result = redact_source_document(document, PrivacyConfig())

        self.assertTrue(result.enabled)
        payload = result.document.model_dump_json(exclude={"content": {"attachments"}})
        self.assertNotIn("alice@example.com", payload)
        self.assertNotIn("13800138000", payload)
        self.assertNotIn("sk-1234567890abcdefghijklmnop", payload)
        self.assertNotIn("sk-abcdefghijklmnop1234567890", payload)
        self.assertNotIn("cli_aa9f1cd454399bc8", payload)
        self.assertNotIn("/Users/alice", payload)
        self.assertNotIn("PRIVATE KEY-----secret", payload)
        self.assertGreaterEqual(result.counts["emails"], 2)
        self.assertEqual(result.counts["phone_numbers"], 2)
        self.assertEqual(result.counts["api_keys"], 1)
        self.assertEqual(result.counts["env_secrets"], 1)
        self.assertEqual(result.counts["platform_ids"], 1)
        self.assertEqual(result.document.metadata["redaction"]["enabled"], True)
        attachment = result.document.content.attachments[0]
        self.assertEqual(
            attachment["content_hash"],
            "11602df6040f9fef74f63e0f44eadfe2f3ec4f14967004112cd292b1e583783f",
        )
        self.assertEqual(
            attachment["relative_path"],
            "raw/derived/assets/images/11602df6040f9fef74f63e0f44eadfe2f3ec4f14967004112cd292b1e583783f.jpg",
        )
        self.assertEqual(attachment["path"], "/Users/alice/Desktop/image.png")
        self.assertEqual(attachment["description"], "Call [REDACTED_PHONE] for the figure.")

    def test_public_text_redaction_reports_counts_without_counting_placeholders(self) -> None:
        text = "Use cli_aa9f1cd454399bc8 from /Users/alice/project, not `/Users/[REDACTED_USER]`."

        result = redact_public_text(text, PrivacyConfig())

        self.assertIn("[REDACTED_PLATFORM_ID]", result.text)
        self.assertIn("/Users/[REDACTED_USER]/project", result.text)
        self.assertIn("`/Users/[REDACTED_USER]`", result.text)
        self.assertEqual(result.counts["platform_ids"], 1)
        self.assertEqual(result.counts["local_paths"], 1)
        self.assertEqual(detect_sensitive_text(result.text, PrivacyConfig()), {})

    def test_does_not_redact_lowercase_technical_token_parameters_or_hashes(self) -> None:
        text = "\n".join(
            [
                "content_hash: 5537701672cc",
                "Fix: set max_tokens=1024 timeout=120s",
                "Prefill effective tokens = prompt length; Decode effective tokens = 1 per request.",
                "FEISHU_APP_SECRET=your_secret",
                "cache path /home/app/.cache/tool",
            ]
        )

        result = redact_public_text(text, PrivacyConfig())

        self.assertIn("content_hash: 5537701672cc", result.text)
        self.assertIn("max_tokens=1024", result.text)
        self.assertIn("effective tokens = prompt length", result.text)
        self.assertIn("/home/app/.cache/tool", result.text)
        self.assertIn("FEISHU_APP_SECRET=[REDACTED_SECRET]", result.text)
        self.assertEqual(result.counts, {"env_secrets": 1})
        self.assertEqual(detect_sensitive_text(result.text, PrivacyConfig()), {})

    def test_redacts_user_configured_custom_terms(self) -> None:
        config = PrivacyConfig(custom_terms=["曹钢", "pxcg@MacBookAir"])
        text = "user 曹钢 on host pxcg@MacBookAir"

        result = redact_public_text(text, config)

        self.assertEqual(result.text, "user [REDACTED_CUSTOM] on host [REDACTED_CUSTOM]")
        self.assertEqual(result.counts, {"custom_terms": 2})
        self.assertEqual(detect_sensitive_text(result.text, config), {})

    def test_can_disable_redaction(self) -> None:
        document = make_document("Email alice@example.com")

        result = redact_source_document(document, PrivacyConfig(redaction_enabled=False))

        self.assertFalse(result.enabled)
        self.assertIs(result.document, document)
        self.assertEqual(result.counts, {})


if __name__ == "__main__":
    unittest.main()
