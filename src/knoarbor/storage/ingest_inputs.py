from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from uuid import uuid4

from knoarbor.core.errors import InternalKnoArborError
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.storage.vault_layout import raw_derived_assets_root


INPUT_GENERATION_SCHEMA = "ingest_input_generation.v1"


class InputGenerationIntegrityError(InternalKnoArborError):
    """An immutable input generation failed identity or containment checks."""


@dataclass(frozen=True)
class InputGeneration:
    generation_id: str
    path: Path
    documents: list[SourceDocument]
    failures: list[dict[str, object]]
    metadata: dict[str, object]


def input_generations_root(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve() / ".knoarbor" / "ingest_inputs" / "generations"


def write_input_generation(
    vault_path: Path,
    *,
    documents: list[SourceDocument],
    failures: list[dict[str, object]] | None = None,
    metadata: dict[str, object] | None = None,
) -> InputGeneration:
    vault = vault_path.expanduser().resolve()
    retained = [_retain_local_attachments(vault, document) for document in documents]
    ordered = sorted(retained, key=lambda item: (item.source_id, item.fingerprint.content_hash))
    failure_items = sorted(failures or [], key=_canonical_json)
    metadata_payload = metadata or {}
    staging = input_generations_root(vault) / ".staging" / uuid4().hex
    staging.mkdir(parents=True, exist_ok=False)
    files: list[dict[str, str]] = []
    try:
        for index, document in enumerate(ordered):
            name = f"documents/{index:06d}.json"
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(path, document.model_dump(mode="json"))
            files.append({"path": name, "sha256": _file_hash(path)})
        generation_payload = {
            "schema_version": INPUT_GENERATION_SCHEMA,
            "documents": [
                {
                    "source_id": document.source_id,
                    "content_hash": document.fingerprint.content_hash,
                    "path": files[index]["path"],
                }
                for index, document in enumerate(ordered)
            ],
            "files": files,
            "failures": failure_items,
            "metadata": metadata_payload,
        }
        generation_id = f"sha256:{sha256(_canonical_json(generation_payload).encode('utf-8')).hexdigest()}"
        manifest = {**generation_payload, "generation_id": generation_id}
        _write_json(staging / "manifest.json", manifest)
        target = input_generations_root(vault) / generation_id.removeprefix("sha256:")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(staging)
        else:
            staging.replace(target)
        return read_input_generation(vault, generation_id)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def read_input_generation(vault_path: Path, generation_id: str) -> InputGeneration:
    vault = vault_path.expanduser().resolve()
    digest = _generation_digest(generation_id)
    path = input_generations_root(vault) / digest
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise InputGenerationIntegrityError(f"Ingest input generation is missing: {generation_id}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputGenerationIntegrityError(f"Ingest input generation manifest is unreadable: {generation_id}") from exc
    if not isinstance(manifest, dict):
        raise InputGenerationIntegrityError(f"Ingest input generation manifest is invalid: {generation_id}")
    if manifest.get("schema_version") != INPUT_GENERATION_SCHEMA or manifest.get("generation_id") != generation_id:
        raise InputGenerationIntegrityError(f"Ingest input generation manifest is invalid: {generation_id}")
    canonical = {key: value for key, value in manifest.items() if key != "generation_id"}
    actual_id = f"sha256:{sha256(_canonical_json(canonical).encode('utf-8')).hexdigest()}"
    if actual_id != generation_id:
        raise InputGenerationIntegrityError(f"Ingest input generation identity failed verification: {generation_id}")
    file_items = manifest.get("files")
    document_items = manifest.get("documents")
    if not isinstance(file_items, list) or not isinstance(document_items, list):
        raise InputGenerationIntegrityError(f"Ingest input generation inventory is invalid: {generation_id}")
    verified_files: dict[str, Path] = {}
    for item in file_items:
        if not isinstance(item, dict):
            raise InputGenerationIntegrityError(f"Ingest input generation file entry is invalid: {generation_id}")
        member = str(item.get("path") or "")
        file_path = _generation_member_path(path, member, generation_id)
        if member in verified_files:
            raise InputGenerationIntegrityError(f"Ingest input generation contains duplicate file path: {member}")
        if not file_path.is_file() or _file_hash(file_path) != item.get("sha256"):
            raise InputGenerationIntegrityError(
                f"Ingest input generation file failed verification: {generation_id} ({member})"
            )
        verified_files[member] = file_path
    documents: list[SourceDocument] = []
    for item in document_items:
        if not isinstance(item, dict):
            raise InputGenerationIntegrityError(f"Ingest input generation document entry is invalid: {generation_id}")
        member = str(item.get("path") or "")
        document_path = _generation_member_path(path, member, generation_id)
        if verified_files.get(member) != document_path:
            raise InputGenerationIntegrityError(
                f"Ingest input generation document is absent from verified inventory: {generation_id} ({member})"
            )
        try:
            documents.append(SourceDocument.model_validate_json(document_path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise InputGenerationIntegrityError(
                f"Ingest input generation document failed validation: {generation_id} ({member})"
            ) from exc
    failures = [dict(item) for item in manifest.get("failures", []) if isinstance(item, dict)]
    metadata = dict(manifest.get("metadata", {})) if isinstance(manifest.get("metadata"), dict) else {}
    return InputGeneration(generation_id, path, documents, failures, metadata)


def _generation_digest(generation_id: str) -> str:
    prefix = "sha256:"
    digest = generation_id.removeprefix(prefix)
    if (
        not generation_id.startswith(prefix)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise InputGenerationIntegrityError(f"Ingest input generation id is invalid: {generation_id}")
    return digest


def _generation_member_path(generation_path: Path, member: str, generation_id: str) -> Path:
    if not member or "\\" in member:
        raise InputGenerationIntegrityError(
            f"Ingest input generation member path is invalid: {generation_id} ({member!r})"
        )
    relative = PurePosixPath(member)
    if relative.is_absolute() or relative.as_posix() != member or any(part in {"", ".", ".."} for part in relative.parts):
        raise InputGenerationIntegrityError(
            f"Ingest input generation member path is invalid: {generation_id} ({member!r})"
        )
    resolved = (generation_path / Path(*relative.parts)).resolve()
    if not resolved.is_relative_to(generation_path.resolve()):
        raise InputGenerationIntegrityError(
            f"Ingest input generation member escapes its generation: {generation_id} ({member!r})"
        )
    return resolved


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _retain_local_attachments(vault: Path, document: SourceDocument) -> SourceDocument:
    retained: list[dict[str, object]] = []
    for attachment in document.content.attachments:
        if not isinstance(attachment, dict):
            continue
        source_value = str(attachment.get("path") or "").strip()
        source = Path(source_value).expanduser().resolve() if source_value else None
        if source is None or not source.is_file():
            retained.append(dict(attachment))
            continue
        data = source.read_bytes()
        digest = sha256(data).hexdigest()
        category = "images" if str(attachment.get("attachment_type") or "") == "image" else "media"
        suffix = source.suffix.lower()
        target = raw_derived_assets_root(vault) / category / f"{digest}{suffix}"
        _write_content_addressed_asset(target, data, digest)
        payload = dict(attachment)
        payload.pop("path", None)
        payload["relative_path"] = target.relative_to(vault).as_posix()
        payload["content_hash"] = digest
        retained.append(payload)
    content = document.content.model_copy(update={"attachments": retained})
    return document.model_copy(update={"content": content})


def _write_content_addressed_asset(target: Path, data: bytes, digest: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Retained attachment hash collision: {target.name}")
        return
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
