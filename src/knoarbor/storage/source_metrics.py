from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.runtime import vault_write_lock


def source_metrics_path(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve() / ".knoarbor" / "metrics" / "source_counts.json"


def source_metric_key(*, category: str, name: str, path: str | None, pattern: str | None) -> str:
    return json.dumps({"category": category, "name": name, "path": path or "", "pattern": pattern or ""}, ensure_ascii=False, sort_keys=True)


def connector_source_metric_key(name: str, settings: dict[str, object]) -> str | None:
    identity = connector_source_metric_identity(name, settings)
    if identity is None:
        return None
    return source_metric_key(category="connector", name=name, path=identity["path"], pattern=identity["pattern"])


def connector_source_metric_identity(name: str, settings: dict[str, object]) -> dict[str, str] | None:
    if name == "codex":
        return _single_path_identity(settings, "sessions_dir", "rollout-*.jsonl")
    if name == "hermes":
        return _single_path_identity(settings, "sessions_dir", "session_*.json")
    if name in {"openclaw", "claude_code"}:
        return _single_path_identity(settings, "sessions_dir", "*.jsonl")
    if name == "markdown":
        return _multi_path_identity(settings, "roots", str(settings.get("pattern") or "*.md"))
    if name == "generic_chat":
        return _multi_path_identity(settings, "roots", "*")
    return None


def _single_path_identity(settings: dict[str, object], key: str, default_pattern: str) -> dict[str, str] | None:
    value = settings.get(key)
    if not value:
        return None
    return {"path": str(Path(str(value)).expanduser()), "pattern": str(settings.get("pattern") or default_pattern)}


def _multi_path_identity(settings: dict[str, object], key: str, pattern: str) -> dict[str, str] | None:
    values = [str(Path(str(item)).expanduser()) for item in settings.get(key, []) if item]
    if not values:
        return None
    return {"path": ", ".join(values), "pattern": pattern}


def load_source_counts(vault_path: Path) -> dict[str, int]:
    path = source_metrics_path(vault_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    counts = payload.get("counts", {})
    if not isinstance(counts, dict):
        return {}
    return {str(key): int(value) for key, value in counts.items() if isinstance(value, int)}


def update_source_counts(vault_path: Path, counts: dict[str, int]) -> None:
    path = source_metrics_path(vault_path)
    existing = load_source_counts(vault_path)
    existing.update(counts)
    payload: dict[str, Any] = {
        "schema_version": "source_counts.v1",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "counts": existing,
    }
    with vault_write_lock(vault_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
