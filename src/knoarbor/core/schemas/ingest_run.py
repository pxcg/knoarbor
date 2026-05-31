from __future__ import annotations

from pydantic import BaseModel, Field

from knoarbor.core.schemas.sources import SourceDocument


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
