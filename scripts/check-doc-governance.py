from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "specs" / "registry.json"
CORE_FILES = ("requirements.md", "design.md", "tasks.md", "verification.md")


def main() -> int:
    errors: list[str] = []
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "knoarbor_spec_registry.v1":
        errors.append("specs/registry.json: unsupported schema_version")
    lifecycles = set(payload.get("lifecycles", []))
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for entry in payload.get("specs", []):
        spec_id = str(entry.get("id", ""))
        spec_path = str(entry.get("path", ""))
        lifecycle = str(entry.get("lifecycle", ""))
        if not spec_id or spec_id in seen_ids:
            errors.append(f"specs/registry.json: duplicate or missing id {spec_id!r}")
        if not spec_path or spec_path in seen_paths:
            errors.append(f"specs/registry.json: duplicate or missing path {spec_path!r}")
        if lifecycle not in lifecycles:
            errors.append(f"specs/registry.json: invalid lifecycle {lifecycle!r} for {spec_id}")
        directory = ROOT / "specs" / spec_path
        if not directory.is_dir():
            errors.append(f"specs/registry.json: missing spec directory specs/{spec_path}")
        else:
            for filename in CORE_FILES:
                if not (directory / filename).is_file():
                    errors.append(f"specs/{spec_path}: missing {filename}")
        seen_ids.add(spec_id)
        seen_paths.add(spec_path)
    registry_paths = {str(entry.get("path", "")) for entry in payload.get("specs", [])}
    for directory in sorted((ROOT / "specs").iterdir()):
        if directory.is_dir() and (directory / "requirements.md").is_file() and directory.name not in registry_paths:
            errors.append(f"specs/{directory.name}: current spec is missing from registry")
    if errors:
        print("\n".join(errors))
        return 1
    print("Documentation governance check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
