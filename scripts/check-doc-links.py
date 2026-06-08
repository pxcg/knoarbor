#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "vaults",
    "web",
    "wiki",
}
LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\n]+)\)")


def iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return sorted(files)


def normalize_target(raw: str) -> str | None:
    target = raw.strip()
    if not target or target.startswith("#"):
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        return None
    return unquote(target.split("#", 1)[0]).strip()


def resolve_link(source: Path, target: str) -> Path:
    candidate = (source.parent / target).resolve()
    if candidate.exists():
        return candidate
    if candidate.suffix:
        return candidate
    md_candidate = candidate.with_suffix(".md")
    if md_candidate.exists():
        return md_candidate
    return candidate


def main() -> int:
    missing: list[str] = []
    files = iter_markdown_files()
    for source in files:
        text = source.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = normalize_target(match.group(1))
            if target is None:
                continue
            resolved = resolve_link(source, target)
            if not resolved.exists():
                missing.append(f"{source.relative_to(ROOT)} -> {target}")

    if missing:
        print("Broken local Markdown links:")
        for item in missing:
            print(f"- {item}")
        return 1

    print(f"Checked {len(files)} Markdown files. No broken local links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
