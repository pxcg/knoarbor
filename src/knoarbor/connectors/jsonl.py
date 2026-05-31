from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JsonlReadResult:
    records: list[tuple[int, dict[str, object]]]
    warnings: list[str]


def read_jsonl_records(path: Path, *, source_name: str) -> JsonlReadResult:
    """Read best-effort JSONL records for local chat session exports.

    Chat tools can leave a JSONL file with an incomplete trailing line while a
    session is still being written. Connector parsing owns that source-format
    tolerance: malformed lines are skipped with explicit warnings instead of
    leaking provider-specific file noise into ingest or semantic contracts.
    """

    records: list[tuple[int, dict[str, object]]] = []
    warnings: list[str] = []
    for raw_index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            warnings.append(
                f"Skipped malformed {source_name} JSONL line {raw_index}: {exc.msg} "
                f"at column {exc.colno}."
            )
            continue
        if isinstance(value, dict):
            records.append((raw_index, value))
        else:
            warnings.append(f"Skipped non-object {source_name} JSONL line {raw_index}.")
    return JsonlReadResult(records=records, warnings=warnings)
