from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel, Field

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.schemas.sources import SourceDocument


_ATTACHMENT_MACHINE_FIELDS = {
    "attachment_id",
    "attachment_type",
    "content_hash",
    "markdown_target",
    "mime_type",
    "obsidian_target",
    "path",
    "relative_path",
    "source",
    "thumbnail_hash",
    "thumbnail_path",
}


class SourceRedactionResult(BaseModel):
    document: SourceDocument
    enabled: bool = True
    counts: dict[str, int] = Field(default_factory=dict)


class TextRedactionResult(BaseModel):
    text: str
    enabled: bool = True
    counts: dict[str, int] = Field(default_factory=dict)


def redact_source_document(document: SourceDocument, config: PrivacyConfig) -> SourceRedactionResult:
    """Return a redacted copy for model input while leaving the raw source intact."""

    if not config.redaction_enabled:
        return SourceRedactionResult(document=document, enabled=False)

    counts: dict[str, int] = {}
    redacted = document.model_copy(deep=True)
    redacted.content.text = _redact_text(redacted.content.text, config, counts)
    redacted.content.sections = _redact_value(redacted.content.sections, config, counts)
    redacted.content.attachments = [
        _redact_attachment(attachment, config, counts)
        for attachment in redacted.content.attachments
    ]
    redacted.origin.uri = _redact_text(redacted.origin.uri, config, counts)
    redacted.origin.raw_path = _redact_text(redacted.origin.raw_path, config, counts)
    if redacted.origin.original_path:
        redacted.origin.original_path = _redact_text(redacted.origin.original_path, config, counts)
    redacted.metadata = _redact_value(redacted.metadata, config, counts)
    redacted.metadata["redaction"] = {
        "enabled": True,
        "counts": dict(counts),
    }
    return SourceRedactionResult(document=redacted, counts=counts)


def redact_display_text(text: str, config: PrivacyConfig) -> str:
    """Redact a single display value using the configured privacy rules.

    This is for public-facing wiki/report text. It intentionally does not
    mutate machine provenance such as checkpoints, raw source paths, or
    connector state.
    """

    if not config.redaction_enabled:
        return text
    counts: dict[str, int] = {}
    return _redact_text(text, config, counts)


def redact_public_text(text: str, config: PrivacyConfig) -> TextRedactionResult:
    """Redact wiki/report-facing text and return redaction counts."""

    if not config.redaction_enabled:
        return TextRedactionResult(text=text, enabled=False)
    counts: dict[str, int] = {}
    redacted = _redact_text(text, config, counts)
    return TextRedactionResult(text=redacted, counts=counts)


def detect_sensitive_text(text: str, config: PrivacyConfig) -> dict[str, int]:
    """Return redaction counts without exposing the matched sensitive values."""

    return redact_public_text(text, config).counts


def _redact_value(value: Any, config: PrivacyConfig, counts: dict[str, int]) -> Any:
    if isinstance(value, str):
        return _redact_text(value, config, counts)
    if isinstance(value, list):
        return [_redact_value(item, config, counts) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item, config, counts) for key, item in value.items()}
    return value


def _redact_attachment(
    value: dict[str, Any],
    config: PrivacyConfig,
    counts: dict[str, int],
) -> dict[str, Any]:
    """Redact descriptive attachment text without changing locator identity."""

    return {
        key: item if key in _ATTACHMENT_MACHINE_FIELDS else _redact_value(item, config, counts)
        for key, item in value.items()
    }


def _redact_text(text: str, config: PrivacyConfig, counts: dict[str, int]) -> str:
    if not text:
        return text

    redacted = text
    for term in config.custom_terms:
        clean_term = term.strip()
        if clean_term:
            redacted = _sub_counted(
                "custom_terms",
                re.escape(clean_term),
                "[REDACTED_CUSTOM]",
                redacted,
                counts,
            )
    if config.redact_private_keys:
        redacted = _sub_counted(
            "private_keys",
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            "[REDACTED_PRIVATE_KEY]",
            redacted,
            counts,
            flags=re.DOTALL,
        )
    if config.redact_api_keys:
        redacted = _sub_counted(
            "env_secrets",
            r"\b([A-Z][A-Z0-9_]*(?:API_KEY|ACCESS_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)\s*=\s*(?!\[REDACTED_SECRET\](?:\s|$))([^\s\"'`]+)",
            lambda match: f"{match.group(1)}=[REDACTED_SECRET]",
            redacted,
            counts,
        )
        redacted = _sub_counted(
            "api_keys",
            r"\bsk-[A-Za-z0-9_-]{16,}\b",
            "[REDACTED_API_KEY]",
            redacted,
            counts,
        )
        redacted = _sub_counted(
            "bearer_tokens",
            r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}",
            "Bearer [REDACTED_TOKEN]",
            redacted,
            counts,
            flags=re.IGNORECASE,
        )
    if config.redact_platform_ids:
        redacted = _sub_counted(
            "platform_ids",
            r"\bcli_[A-Za-z0-9]{12,}\b",
            "[REDACTED_PLATFORM_ID]",
            redacted,
            counts,
        )
    if config.redact_emails:
        redacted = _sub_counted(
            "emails",
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "[REDACTED_EMAIL]",
            redacted,
            counts,
        )
    if config.redact_phone_numbers:
        redacted = _sub_counted(
            "phone_numbers",
            r"(?<![A-Fa-f0-9])(?:\+?86[-.\s]?)?1[3-9]\d{9}(?![A-Fa-f0-9])",
            "[REDACTED_PHONE]",
            redacted,
            counts,
        )
        redacted = _sub_counted(
            "phone_numbers",
            r"(?<![A-Fa-f0-9])(?:\+1[-.\s]?|\(\d{3}\)[-.\s]?|\d{3}[-.\s])\d{3}[-.\s]?\d{4}(?![A-Fa-f0-9])",
            "[REDACTED_PHONE]",
            redacted,
            counts,
        )
    if config.redact_local_paths:
        redacted = _sub_counted(
            "local_paths",
            r"(?<!\w)/(?:Users|home)/(?!(?:\[REDACTED_USER\]|app|node)(?:/|\s|`|$))[^/\s`]+",
            lambda match: "/".join([match.group(0).split("/")[0], match.group(0).split("/")[1], "[REDACTED_USER]"]),
            redacted,
            counts,
        )
        redacted = _sub_counted(
            "local_paths",
            r"\b([A-Za-z]:\\Users\\)(?!\[REDACTED_USER\](?:\\|\s|`|$))[^\\\s`]+",
            r"\1[REDACTED_USER]",
            redacted,
            counts,
        )
    if config.redact_private_ips:
        redacted = _sub_counted(
            "private_ips",
            r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b",
            "[REDACTED_PRIVATE_IP]",
            redacted,
            counts,
        )
    return redacted


def _sub_counted(
    key: str,
    pattern: str,
    repl: str | Callable[[re.Match[str]], str],
    text: str,
    counts: dict[str, int],
    *,
    flags: int = 0,
) -> str:
    redacted, count = re.subn(pattern, repl, text, flags=flags)
    if count:
        counts[key] = counts.get(key, 0) + count
    return redacted
