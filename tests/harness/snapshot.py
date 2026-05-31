from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def canonical_json(value: Any) -> str:
    """Stable JSON representation for contract golden assertions."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def assert_json_snapshot(testcase: object, value: Any, snapshot_path: Path) -> None:
    expected = snapshot_path.read_text(encoding="utf-8")
    actual = canonical_json(value)
    assert_method = getattr(testcase, "assertEqual")
    assert_method(actual, expected)
