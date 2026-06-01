from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from knoarbor.core.schemas.sources import SourceDocument

IngestRequestKind = Literal["connectors", "document", "file"]


class IngestRunRequest(BaseModel):
    config_path: str | None = None
    connector_names: list[str] | None = Field(default=None, min_length=1)
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    recovery_of_run_id: str | None = None


class IngestDocumentRunRequest(BaseModel):
    source_document: SourceDocument
    config_path: str | None = None
    obsidian_vault_path: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    auto_scoped_lint: bool | None = None
    auto_apply_safe_lint_fixes: bool | None = None
    scoped_lint_include_related: bool | None = None


class IngestFileRunRequest(BaseModel):
    input_path: str
    config_path: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
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
    config_path: str | None = None
    connector_names: list[str] | None = Field(default=None, min_length=1)
    source_document: SourceDocument | None = None
    input_path: str | None = None
    obsidian_vault_path: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    recovery_of_run_id: str | None = None
    auto_scoped_lint: bool | None = None
    auto_apply_safe_lint_fixes: bool | None = None
    scoped_lint_include_related: bool | None = None

    @model_validator(mode="after")
    def validate_kind_payload(self) -> "UnifiedIngestRequest":
        if self.kind == "document" and self.source_document is None:
            raise ValueError("source_document is required when kind='document'.")
        if self.kind == "file" and not self.input_path:
            raise ValueError("input_path is required when kind='file'.")
        return self

    def to_connectors_request(self) -> IngestRunRequest:
        return IngestRunRequest(
            config_path=self.config_path,
            connector_names=self.connector_names,
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            recovery_of_run_id=self.recovery_of_run_id,
        )

    def to_document_request(self) -> IngestDocumentRunRequest:
        if self.source_document is None:
            raise ValueError("source_document is required when kind='document'.")
        return IngestDocumentRunRequest(
            source_document=self.source_document,
            config_path=self.config_path,
            obsidian_vault_path=self.obsidian_vault_path,
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
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            recovery_of_run_id=self.recovery_of_run_id,
        )
