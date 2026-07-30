from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord


@dataclass(frozen=True)
class FactCommit:
    processing_record: SourceProcessingRecord
    atom_batch: KnowledgeAtomBatch
    diagnostics: dict[str, object] = field(default_factory=dict)
    window_id: str | None = None
    window_from_index: int | None = None
    window_to_index: int | None = None
    checkpoint_cursor: dict[str, object] | None = None


@dataclass(frozen=True)
class FactIdentity:
    source_id: str
    raw_revision_id: str
    window_id: str | None = None


@dataclass(frozen=True)
class PublishedFact:
    revision_id: str
    generation_path: Path


class IngestExecutionPort(Protocol):
    def before_model_call(self) -> None: ...

    def find_published_fact(self, identity: FactIdentity) -> PublishedFact | None: ...

    def publish_fact(self, commit: FactCommit) -> PublishedFact: ...


class IngestExecutionCommand(BaseModel):
    schema_version: Literal["ingest_execution_command.v2"] = "ingest_execution_command.v2"
    generation_id: str = Field(..., pattern=r"^sha256:[0-9a-f]{64}$")
    request_kind: str
    config_path: str | None = None
    vault_id: str | None = None
    vault_path: str
    vault_identity: str
    provider: str | None = None
    max_tokens: int | None = None
    write: bool
    write_report: bool
    append_ledger: bool
    force_reprocess: bool = False
    force_invocation_id: str | None = None
    execution_contract: dict[str, object]
    execution_contract_hash: str
    factual_contract_hash: str | None = None

    def command_hash(self) -> str:
        return _hash(self.model_dump(mode="json"))


def execution_contract_hash(contract: dict[str, object]) -> str:
    return _hash(contract)


def provider_admission_key(command: IngestExecutionCommand) -> str:
    provider = command.execution_contract.get("provider")
    payload = provider if isinstance(provider, dict) else {}
    return f"{payload.get('name') or ''}:{payload.get('model') or ''}:{payload.get('base_url') or ''}"


def fact_input_revision_key(command: IngestExecutionCommand, identity: FactIdentity) -> str:
    factual_contract_hash = command.factual_contract_hash or command.execution_contract_hash
    return _hash(
        {
            "factual_contract_hash": factual_contract_hash,
            "source_id": identity.source_id,
            "raw_revision_id": identity.raw_revision_id,
            "window_id": identity.window_id,
            "force_invocation_id": command.force_invocation_id if command.force_reprocess else None,
        }
    )


def _hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"
