from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knoarbor.storage import ensure_machine_index, machine_index_dir


def load_graph_index(vault_path: Path) -> dict[str, Any]:
    ensure_machine_index(vault_path)
    path = machine_index_dir(vault_path) / "graph_index.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}
