from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from knoarbor.storage.vault_layout import runtime_index_root
from knoarbor.storage.lexical_snapshot import verify_lexical_snapshot


INDEX_ARTIFACTS = frozenset({"graph_index.json", "pages.json", "links.json", "sources.json", "search.json", "retrieval.sqlite"})


@dataclass(frozen=True)
class IndexSnapshot:
    generation_id: str
    path: Path
    manifest: dict[str, Any]

    @property
    def retrieval_path(self) -> Path:
        return self.path / "retrieval.sqlite"

    @property
    def retrieval_generation_id(self) -> str:
        return str(self.manifest["retrieval_generation_id"])

    @property
    def active_fact_generation(self) -> str:
        return str(self.manifest["active_fact_generation"])


def open_index_snapshot(
    vault_path: Path,
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
) -> IndexSnapshot | None:
    root = runtime_index_root(vault_path)
    current = root / "CURRENT"
    if not current.is_file():
        return None
    generation_id = current.read_text(encoding="utf-8").strip()
    if not generation_id or "/" in generation_id or "\\" in generation_id:
        raise RuntimeError("Machine index CURRENT pointer is invalid.")
    return open_index_generation(vault_path, generation_id, raise_if_cancelled=raise_if_cancelled)


def open_index_generation(
    vault_path: Path,
    generation_id: str,
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
) -> IndexSnapshot:
    root = runtime_index_root(vault_path)
    if not generation_id or "/" in generation_id or "\\" in generation_id:
        raise RuntimeError("Machine index generation id is invalid.")
    path = root / "generations" / generation_id
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Machine index generation is missing: {generation_id}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Machine index manifest is invalid: {generation_id}") from exc
    if manifest.get("generation_id") != generation_id:
        raise RuntimeError("Machine index manifest does not match its generation directory.")
    if manifest.get("identity_schema") != "index_generation_identity.v4":
        raise RuntimeError("Machine index generation identity schema is unsupported.")
    for field in (
        "navigation_generation_id",
        "retrieval_generation_id",
        "active_fact_generation",
    ):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise RuntimeError(f"Machine index composite generation field is invalid: {field}")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != INDEX_ARTIFACTS:
        raise RuntimeError("Machine index manifest artifact set is invalid.")
    for name, expected in files.items():
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        artifact = path / str(name)
        if not artifact.is_file() or _file_hash(artifact, raise_if_cancelled=raise_if_cancelled) != expected:
            raise RuntimeError(f"Machine index artifact failed verification: {name}")
    _validate_index_artifacts(path, raise_if_cancelled=raise_if_cancelled)
    verify_lexical_snapshot(
        path / "retrieval.sqlite",
        expected_fact_generation=str(manifest["active_fact_generation"]),
        raise_if_cancelled=raise_if_cancelled,
    )
    if index_generation_id(manifest) != generation_id:
        raise RuntimeError("Machine index generation identity failed verification.")
    return IndexSnapshot(generation_id=generation_id, path=path, manifest=manifest)


def canonical_index_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def index_generation_id(manifest: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in manifest.items()
        if key not in {"generation_id", "generated_at", "vault_path"}
    }
    return sha256(canonical_index_json(stable)).hexdigest()


def _validate_index_artifacts(
    path: Path,
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
) -> None:
    contracts = {
        "pages.json": ("machine_pages.v2", "pages"),
        "links.json": ("machine_links.v1", "links"),
        "sources.json": ("machine_sources.v1", "sources"),
        "search.json": ("machine_search.v1", "entries"),
    }
    for name, (schema, collection) in contracts.items():
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        payload = json.loads((path / name).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != schema or not isinstance(payload.get(collection), list):
            raise RuntimeError(f"Machine index artifact schema is invalid: {name}")
    graph = json.loads((path / "graph_index.json").read_text(encoding="utf-8"))
    if (
        not isinstance(graph, dict)
        or graph.get("schema_version") != "knoarbor_graph_index.v1"
        or any(not isinstance(graph.get(name), list) for name in ("nodes", "edges", "sources"))
    ):
        raise RuntimeError("Machine index artifact schema is invalid: graph_index.json")
    pages = json.loads((path / "pages.json").read_text(encoding="utf-8"))["pages"]
    if any(not isinstance(page, dict) or not isinstance(page.get("body"), str) for page in pages):
        raise RuntimeError("Machine index page snapshot body is invalid.")


def _file_hash(
    path: Path,
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if raise_if_cancelled is not None:
                raise_if_cancelled()
            digest.update(chunk)
    return digest.hexdigest()
