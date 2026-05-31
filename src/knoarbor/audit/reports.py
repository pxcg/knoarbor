from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from knoarbor.runtime import vault_write_lock


def write_maintenance_report(vault_path: Path, report_kind: str, content: str, report_path: str | None = None) -> Path:
    """Write a user-readable maintenance report under the configured vault."""

    if report_path:
        output_path = (vault_path / report_path.strip().lstrip("/")).resolve()
        output_path.relative_to(vault_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_kind = re.sub(r"[^a-zA-Z0-9_-]+", "_", report_kind.strip().lower() or "custom").strip("_")
        output_path = vault_path / "maintenance" / f"{safe_kind}_report_{timestamp}.md"

    with vault_write_lock(vault_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
    return output_path
