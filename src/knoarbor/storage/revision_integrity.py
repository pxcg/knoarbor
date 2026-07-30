from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path, PurePosixPath


def revision_manifest_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(encoded.encode('utf-8')).hexdigest()}"


def revision_file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def verify_revision_generation(vault_path: Path, revision: dict[str, object]) -> Path:
    vault = vault_path.expanduser().resolve()
    relative = _safe_relative_path(revision.get("manifest_path"), field="manifest_path")
    generation = (vault / Path(*relative.parts)).resolve()
    if not generation.is_relative_to(vault):
        raise RuntimeError("Published source revision path escapes the vault.")
    return verify_revision_generation_path(generation, revision)


def verify_revision_generation_path(generation: Path, revision: dict[str, object]) -> Path:
    revision_id = str(revision.get("revision_id") or "")
    if not revision_id:
        raise RuntimeError("Published source revision has no revision identity.")

    root = generation.expanduser().resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Published source revision is missing its manifest: {revision_id}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Published source revision manifest is unreadable: {revision_id}") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Published source revision manifest is invalid: {revision_id}")
    if manifest.get("revision_id") != revision_id:
        raise RuntimeError(f"Published source revision identity does not match its manifest: {revision_id}")

    expected = str(revision.get("manifest_hash") or "")
    actual = revision_manifest_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
    if not expected or manifest.get("manifest_hash") != expected or actual != expected:
        raise RuntimeError(f"Published source revision manifest failed integrity verification: {revision_id}")

    file_hashes = manifest.get("file_hashes")
    if not isinstance(file_hashes, dict) or not file_hashes:
        raise RuntimeError(f"Published source revision has no file integrity manifest: {revision_id}")
    for name, file_hash in file_hashes.items():
        relative = _safe_relative_path(name, field="file_hashes")
        path = (root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(root) or not path.is_file() or revision_file_hash(path) != file_hash:
            raise RuntimeError(
                f"Published source revision file failed integrity verification: {revision_id} ({name})"
            )
    return root


def _safe_relative_path(value: object, *, field: str) -> PurePosixPath:
    text = str(value or "")
    relative = PurePosixPath(text)
    if (
        not text
        or relative.is_absolute()
        or "\\" in text
        or relative.as_posix() != text
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(f"Published source revision contains an invalid {field} path.")
    return relative
