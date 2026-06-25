from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from knoarbor.core.schemas.execution import WorkflowExecutionMode
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin

IngestRequestKind = Literal["connectors", "document", "excerpt", "file", "folder", "recovery"]


class IngestExcerptContext(BaseModel):
    """Optional provenance for user-selected chat or note excerpts."""

    source_app: str | None = None
    session_id: str | None = None
    message_ids: list[str] = Field(default_factory=list)
    turn_ids: list[str] = Field(default_factory=list)
    source_title: str | None = None
    source_uri: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("message_ids", "turn_ids", mode="before")
    @classmethod
    def normalize_text_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        output: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in output:
                output.append(text)
        return output


class IngestRunRequest(BaseModel):
    config_path: str | None = None
    vault_path: str | None = None
    vault_id: str | None = None
    connector_names: list[str] | None = Field(default=None, min_length=1)
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    force_reprocess: bool = False
    recovery_of_run_id: str | None = None


class IngestDocumentRunRequest(BaseModel):
    source_document: SourceDocument
    config_path: str | None = None
    vault_path: str | None = None
    vault_id: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    auto_scoped_lint: bool | None = None
    auto_apply_safe_lint_fixes: bool | None = None
    scoped_lint_include_related: bool | None = None


class IngestExcerptRunRequest(BaseModel):
    text: str = Field(..., min_length=1)
    title: str | None = None
    context: IngestExcerptContext = Field(default_factory=IngestExcerptContext)
    config_path: str | None = None
    vault_path: str | None = None
    vault_id: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    auto_scoped_lint: bool | None = None
    auto_apply_safe_lint_fixes: bool | None = None
    scoped_lint_include_related: bool | None = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("excerpt text cannot be empty")
        return text


class IngestFileRunRequest(BaseModel):
    input_kind: Literal["file"] = "file"
    input_path: str
    config_path: str | None = None
    vault_path: str | None = None
    vault_id: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    force_reprocess: bool = False
    recovery_of_run_id: str | None = None


class IngestFolderRunRequest(BaseModel):
    input_kind: Literal["folder"] = "folder"
    input_path: str
    recursive: bool = True
    connector_names: list[str] | None = Field(default=None, min_length=1)
    config_path: str | None = None
    vault_path: str | None = None
    vault_id: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    force_reprocess: bool = False
    recovery_of_run_id: str | None = None


class IngestRecoveryRunRequest(BaseModel):
    config_path: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool | None = None
    write_report: bool | None = None
    append_ledger: bool | None = None


class UnifiedIngestRequest(BaseModel):
    """Public ingest request facade.

    `kind` selects the ingest source shape while keeping one public HTTP path.
    The narrow request classes remain internal service contracts.
    """

    kind: IngestRequestKind = "connectors"
    execution: WorkflowExecutionMode = "queued"
    config_path: str | None = None
    connector_names: list[str] | None = Field(default=None, min_length=1)
    source_document: SourceDocument | None = None
    excerpt_text: str | None = None
    excerpt_title: str | None = None
    excerpt_context: IngestExcerptContext = Field(default_factory=IngestExcerptContext)
    input_path: str | None = None
    recursive: bool = True
    vault_path: str | None = None
    vault_id: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    force_reprocess: bool = False
    recovery_of_run_id: str | None = None
    recovery_vault_path: str | None = None
    auto_scoped_lint: bool | None = None
    auto_apply_safe_lint_fixes: bool | None = None
    scoped_lint_include_related: bool | None = None

    @model_validator(mode="after")
    def validate_kind_payload(self) -> "UnifiedIngestRequest":
        if self.kind == "recovery":
            if self.execution != "queued":
                raise ValueError("kind='recovery' requires execution='queued'.")
            if not self.recovery_of_run_id:
                raise ValueError("recovery_of_run_id is required when kind='recovery'.")
            if not (self.recovery_vault_path or self.vault_path or self.vault_id):
                raise ValueError("recovery_vault_path, vault_path, or vault_id is required when kind='recovery'.")
            if self.source_document is not None or self.input_path:
                raise ValueError("kind='recovery' cannot be combined with source_document or input_path.")
            return self
        if self.kind == "document" and self.source_document is None:
            raise ValueError("source_document is required when kind='document'.")
        if self.kind != "document" and self.source_document is not None:
            raise ValueError("source_document is only valid when kind='document'.")
        if self.kind == "excerpt" and not (self.excerpt_text or "").strip():
            raise ValueError("excerpt_text is required when kind='excerpt'.")
        if self.kind != "excerpt" and (self.excerpt_text is not None or self.excerpt_title is not None):
            raise ValueError("excerpt_text and excerpt_title are only valid when kind='excerpt'.")
        if self.kind in {"file", "folder"} and not self.input_path:
            raise ValueError("input_path is required when kind='file' or kind='folder'.")
        if self.kind not in {"file", "folder"} and self.input_path:
            raise ValueError("input_path is only valid when kind='file' or kind='folder'.")
        if self.recovery_of_run_id:
            raise ValueError("recovery_of_run_id is only valid when kind='recovery'.")
        return self

    def to_connectors_request(self) -> IngestRunRequest:
        return IngestRunRequest(
            config_path=self.config_path,
            vault_path=self.vault_path,
            vault_id=self.vault_id,
            connector_names=self.connector_names,
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            force_reprocess=self.force_reprocess,
            recovery_of_run_id=self.recovery_of_run_id,
        )

    def to_document_request(self) -> IngestDocumentRunRequest:
        if self.source_document is None:
            raise ValueError("source_document is required when kind='document'.")
        return IngestDocumentRunRequest(
            source_document=self.source_document,
            config_path=self.config_path,
            vault_path=self.vault_path,
            vault_id=self.vault_id,
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            auto_scoped_lint=self.auto_scoped_lint,
            auto_apply_safe_lint_fixes=self.auto_apply_safe_lint_fixes,
            scoped_lint_include_related=self.scoped_lint_include_related,
        )

    def to_excerpt_request(self) -> IngestDocumentRunRequest:
        if not self.excerpt_text:
            raise ValueError("excerpt_text is required when kind='excerpt'.")
        return IngestDocumentRunRequest(
            source_document=build_excerpt_source_document(
                text=self.excerpt_text,
                title=self.excerpt_title,
                context=self.excerpt_context,
            ),
            config_path=self.config_path,
            vault_path=self.vault_path,
            vault_id=self.vault_id,
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            auto_scoped_lint=self.auto_scoped_lint,
            auto_apply_safe_lint_fixes=self.auto_apply_safe_lint_fixes,
            scoped_lint_include_related=self.scoped_lint_include_related,
        )

    def to_file_request(self) -> IngestFileRunRequest:
        if not self.input_path:
            raise ValueError("input_path is required when kind='file'.")
        return IngestFileRunRequest(
            input_path=self.input_path,
            config_path=self.config_path,
            vault_path=self.vault_path,
            vault_id=self.vault_id,
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            force_reprocess=self.force_reprocess,
            recovery_of_run_id=self.recovery_of_run_id,
        )

    def to_folder_request(self) -> IngestFolderRunRequest:
        if not self.input_path:
            raise ValueError("input_path is required when kind='folder'.")
        return IngestFolderRunRequest(
            input_path=self.input_path,
            recursive=self.recursive,
            connector_names=self.connector_names,
            config_path=self.config_path,
            vault_path=self.vault_path,
            vault_id=self.vault_id,
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            force_reprocess=self.force_reprocess,
            recovery_of_run_id=self.recovery_of_run_id,
        )


def build_excerpt_source_document(*, text: str, title: str | None = None, context: IngestExcerptContext | None = None) -> SourceDocument:
    excerpt_context = context or IngestExcerptContext()
    clean_text = text.strip()
    identity_payload = {
        "text": clean_text,
        "context": excerpt_context.model_dump(mode="json"),
    }
    content_hash = hashlib.sha256(json.dumps(identity_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    short_hash = content_hash[:16]
    display_title = (title or excerpt_context.source_title or "Selected Excerpt").strip()
    source_app = (excerpt_context.source_app or "excerpt").strip() or "excerpt"
    uri = excerpt_context.source_uri or _excerpt_uri(source_app, excerpt_context, short_hash)
    markdown = f"# {display_title}\n\n## Selected Excerpt\n\n{clean_text}\n"
    return SourceDocument(
        source_id=f"excerpt:{short_hash}",
        source_type="excerpt",
        origin=SourceOrigin(
            connector="excerpt",
            uri=uri,
            raw_path=f"raw/excerpts/{short_hash}.md",
        ),
        content=SourceContent(format="markdown", text=markdown),
        metadata={
            "title": display_title,
            "source_kind": "selected_excerpt",
            "source_app": source_app,
            "excerpt_context": excerpt_context.model_dump(mode="json"),
            "excerpt_chars": len(clean_text),
            "excerpt_lines": len(clean_text.splitlines()),
        },
        fingerprint=SourceFingerprint(content_hash=f"sha256:{content_hash}", connector_version="excerpt@1"),
    )


def _excerpt_uri(source_app: str, context: IngestExcerptContext, short_hash: str) -> str:
    if context.session_id:
        return f"excerpt://{source_app}/{context.session_id}/{short_hash}"
    return f"excerpt://{source_app}/{short_hash}"
