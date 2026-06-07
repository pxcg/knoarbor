from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from knoarbor.core.schemas.execution import WorkflowExecutionMode
from knoarbor.core.schemas.sources import SourceDocument

IngestRequestKind = Literal["connectors", "document", "file", "folder", "recovery"]


class IngestRunRequest(BaseModel):
    config_path: str | None = None
    obsidian_vault_path: str | None = Field(default=None, alias="vault_path")
    vault_id: str | None = None
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
    vault_id: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    auto_scoped_lint: bool | None = None
    auto_apply_safe_lint_fixes: bool | None = None
    scoped_lint_include_related: bool | None = None


class IngestFileRunRequest(BaseModel):
    input_kind: Literal["file"] = "file"
    input_path: str
    config_path: str | None = None
    obsidian_vault_path: str | None = Field(default=None, alias="vault_path")
    vault_id: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
    recovery_of_run_id: str | None = None


class IngestFolderRunRequest(BaseModel):
    input_kind: Literal["folder"] = "folder"
    input_path: str
    recursive: bool = True
    config_path: str | None = None
    obsidian_vault_path: str | None = Field(default=None, alias="vault_path")
    vault_id: str | None = None
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

    model_config = ConfigDict(populate_by_name=True)

    kind: IngestRequestKind = "connectors"
    execution: WorkflowExecutionMode = "queued"
    config_path: str | None = None
    connector_names: list[str] | None = Field(default=None, min_length=1)
    source_document: SourceDocument | None = None
    input_path: str | None = None
    recursive: bool = True
    obsidian_vault_path: str | None = Field(default=None, alias="vault_path")
    vault_id: str | None = None
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = False
    write_report: bool = True
    append_ledger: bool = True
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
            if not (self.recovery_vault_path or self.obsidian_vault_path or self.vault_id):
                raise ValueError("recovery_vault_path, vault_path, or vault_id is required when kind='recovery'.")
            if self.source_document is not None or self.input_path:
                raise ValueError("kind='recovery' cannot be combined with source_document or input_path.")
            return self
        if self.kind == "document" and self.source_document is None:
            raise ValueError("source_document is required when kind='document'.")
        if self.kind != "document" and self.source_document is not None:
            raise ValueError("source_document is only valid when kind='document'.")
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
            vault_path=self.obsidian_vault_path,
            vault_id=self.vault_id,
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
            vault_path=self.obsidian_vault_path,
            vault_id=self.vault_id,
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            recovery_of_run_id=self.recovery_of_run_id,
        )

    def to_folder_request(self) -> IngestFolderRunRequest:
        if not self.input_path:
            raise ValueError("input_path is required when kind='folder'.")
        return IngestFolderRunRequest(
            input_path=self.input_path,
            recursive=self.recursive,
            config_path=self.config_path,
            vault_path=self.obsidian_vault_path,
            vault_id=self.vault_id,
            provider=self.provider,
            max_tokens=self.max_tokens,
            write=self.write,
            write_report=self.write_report,
            append_ledger=self.append_ledger,
            recovery_of_run_id=self.recovery_of_run_id,
        )
