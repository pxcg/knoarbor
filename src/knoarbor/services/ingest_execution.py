from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from knoarbor.core.config import KnoArborConfig, default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand, execution_contract_hash
from knoarbor.core.schemas.ingest_run import UnifiedIngestRequest
from knoarbor.core.vaults import select_config_vault
from knoarbor.semantic.contracts import load_semantic_contract
from knoarbor.storage.ingest_inputs import InputGeneration
from knoarbor.storage.vault_identity import ensure_vault_identity


def build_execution_command(
    request: UnifiedIngestRequest,
    config: KnoArborConfig,
    generation: InputGeneration,
    *,
    resolved_config_path: Path | None = None,
) -> IngestExecutionCommand:
    contract = build_execution_contract(config, request.provider, request.max_tokens)
    resolved_vault_path = config.vault.path.expanduser().resolve()
    recorded_vault_id = None if request.vault_path is not None else request.vault_id or config.active_vault_id()
    return IngestExecutionCommand(
        generation_id=generation.generation_id,
        request_kind=request.kind,
        config_path=str((resolved_config_path or Path(request.config_path or default_config_path())).expanduser().resolve()),
        vault_id=recorded_vault_id,
        vault_path=str(resolved_vault_path),
        vault_identity=ensure_vault_identity(resolved_vault_path),
        provider=request.provider,
        max_tokens=config.models.resolve_max_tokens(request.provider, request.max_tokens),
        write=request.write,
        write_report=request.write_report,
        append_ledger=request.append_ledger,
        force_reprocess=request.force_reprocess,
        force_invocation_id=str(uuid4()) if request.force_reprocess else None,
        execution_contract=contract,
        execution_contract_hash=execution_contract_hash(contract),
        factual_contract_hash=execution_contract_hash(factual_execution_contract(contract)),
    )


def validate_execution_command(command: IngestExecutionCommand, config: KnoArborConfig) -> None:
    resolved_vault_path = config.vault.path.expanduser().resolve()
    if resolved_vault_path != Path(command.vault_path).expanduser().resolve():
        raise UserInputError("The ingest command resolved to a different vault path.")
    if ensure_vault_identity(resolved_vault_path) != command.vault_identity:
        raise UserInputError("The ingest command belongs to a different vault identity.")
    if command.vault_id is not None and config.active_vault_id() != command.vault_id:
        raise UserInputError("The ingest command belongs to a different configured vault.")
    current = build_execution_contract(config, command.provider, command.max_tokens)
    current_hash = execution_contract_hash(current)
    if current_hash != command.execution_contract_hash or current != command.execution_contract:
        raise UserInputError("The ingest execution contract changed; submit a new immutable input generation.")
    if command.factual_contract_hash is not None and command.factual_contract_hash != execution_contract_hash(
        factual_execution_contract(command.execution_contract)
    ):
        raise UserInputError("The ingest factual contract identity is invalid.")


def load_execution_config(command: IngestExecutionCommand) -> KnoArborConfig:
    """Reload the immutable vault selection recorded at command admission."""

    config = load_config(command.config_path or default_config_path())
    if command.vault_id is not None:
        config = select_config_vault(config, vault_id=command.vault_id)
    else:
        config = select_config_vault(config, vault_path=command.vault_path)
    validate_execution_command(command, config)
    return config


def build_execution_contract(
    config: KnoArborConfig,
    provider_name: str | None,
    max_tokens: int | None,
) -> dict[str, object]:
    selected = provider_name or config.models.default_provider
    if not selected:
        raise UserInputError("No model provider selected. Set models.default_provider or pass a provider.")
    provider = config.models.providers.get(selected)
    if provider is None:
        raise UserInputError(f"Unknown model provider: {selected}")
    semantic_contract = load_semantic_contract("index_metadata_extract")
    provider_payload = provider.model_dump(mode="json", exclude={"api_key"})
    concurrency = semantic_concurrency_policy(config)
    return {
        "provider": {"name": selected, **provider_payload},
        "max_tokens": config.models.resolve_max_tokens(selected, max_tokens),
        "request_timeout_seconds": config.models.request_timeout_seconds,
        "retry": config.models.retry.model_dump(mode="json"),
        "ingest": {
            "auto_scoped_lint": config.ingest.auto_scoped_lint,
            "segmentation": config.ingest.segmentation.model_dump(mode="json"),
            "concurrency": concurrency,
        },
        "privacy": config.privacy.model_dump(mode="json"),
        "semantic_contract": {
            "name": semantic_contract.name,
            "schema_version": semantic_contract.schema_version,
            "prompt_sha256": f"sha256:{sha256(semantic_contract.prompt_text.encode('utf-8')).hexdigest()}",
        },
    }


def semantic_concurrency_policy(config: KnoArborConfig) -> dict[str, object]:
    """Freeze the internal adaptive policy without exposing numeric tuning."""

    structural_ceiling = max(1, config.ingest.segmentation.max_segments_per_source)
    return {
        "mode": "adaptive_waves",
        "initial_concurrent_requests": min(2, structural_ceiling),
        "max_concurrent_segments": structural_ceiling,
        "max_concurrent_provider_requests": structural_ceiling,
    }


def factual_execution_contract(contract: dict[str, object]) -> dict[str, object]:
    """Return only settings capable of changing committed factual output."""

    ingest = contract.get("ingest") if isinstance(contract.get("ingest"), dict) else {}
    return {
        "provider": contract.get("provider"),
        "max_tokens": contract.get("max_tokens"),
        "privacy": contract.get("privacy"),
        "semantic_contract": contract.get("semantic_contract"),
        "segmentation": ingest.get("segmentation"),
    }
