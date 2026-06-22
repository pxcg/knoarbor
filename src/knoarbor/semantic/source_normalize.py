from __future__ import annotations

from knoarbor.core.schemas.knowledge_extract import KnowledgeSourceType
from knoarbor.core.schemas.sources import SourceDocument


def build_source_normalize_input(document: SourceDocument) -> dict[str, object]:
    """Build the model input for the source normalize semantic contract."""

    return {
        "source_document": document.model_dump(),
        "source_hint": {
            "source_type": _knowledge_source_type(document),
            "source_app": document.origin.connector,
            "source_id": document.source_id,
            "source_path": document.origin.raw_path,
            "title": document.metadata.get("title") or document.metadata.get("display_name") or document.source_id,
            "created_at": document.origin.created_at,
            "updated_at": document.origin.updated_at,
        },
    }


def _knowledge_source_type(document: SourceDocument) -> KnowledgeSourceType:
    if document.source_type in {"hermes_chat", "codex_chat", "openclaw_chat", "claude_code_chat", "knoarbor_chat", "generic_chat"}:
        return "chat"
    if document.source_type == "markdown":
        return "markdown"
    if document.source_type == "web":
        return "web"
    if document.content.format == "html":
        return "html"
    if document.source_type == "document":
        return "markdown" if document.content.format == "markdown" else "document"
    if document.source_type == "text":
        return "text_note"
    if document.source_type == "excerpt":
        return "text_note"
    return "manual"
