#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9][A-Za-z0-9.-]*)?$")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare KnoArbor release metadata.")
    parser.add_argument("version", help="Release version without leading v, for example 0.5.2")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Release date, default: today")
    args = parser.parse_args()

    if not VERSION_RE.match(args.version):
        print(f"Invalid version: {args.version}", file=sys.stderr)
        return 2
    if dirty_worktree():
        print("Working tree is dirty. Commit or stash changes before preparing release metadata.", file=sys.stderr)
        return 1

    update_pyproject(args.version)
    update_package_init(args.version)
    update_renderer_package(args.version)
    ensure_changelog_section(args.version, args.date)
    ensure_release_note(args.version)

    print(f"Prepared KnoArbor v{args.version} metadata.")
    print("Next steps: fill CHANGELOG.md and docs/releases/v%s.md, then run scripts/release-check.sh." % args.version)
    return 0


def dirty_worktree() -> bool:
    import subprocess

    result = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, stdout=subprocess.PIPE, check=False)
    return bool(result.stdout.strip())


def update_pyproject(version: str) -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^version = ".+?"$', f'version = "{version}"', text, count=1)
    path.write_text(text, encoding="utf-8")


def update_package_init(version: str) -> None:
    path = ROOT / "src" / "knoarbor" / "__init__.py"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'__version__ = ".+?"', f'__version__ = "{version}"', text, count=1)
    path.write_text(text, encoding="utf-8")


def update_renderer_package(version: str) -> None:
    for relative in ["renderer/package.json", "renderer/package-lock.json"]:
        path = ROOT / relative
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        if relative.endswith("package-lock.json") and isinstance(data.get("packages"), dict) and "" in data["packages"]:
            data["packages"][""]["version"] = version
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_changelog_section(version: str, date: str) -> None:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    heading = f"## {version} - {date}"
    if heading in text:
        return
    marker = "## Unreleased\n"
    if marker not in text:
        raise RuntimeError("CHANGELOG.md does not contain an Unreleased section")
    section = f"\n{heading}\n\n### Changed\n\n- TODO: summarize release changes.\n"
    path.write_text(text.replace(marker, marker + section, 1), encoding="utf-8")


def ensure_release_note(version: str) -> None:
    path = ROOT / "docs" / "releases" / f"v{version}.md"
    if path.exists():
        return
    path.write_text(
        f"# KnoArbor v{version}\n\n"
        "TODO: summarize the release focus.\n\n"
        "## Highlights\n\n"
        "- TODO\n\n"
        "## Validation\n\n"
        "- TODO\n\n"
        "## Upgrade Notes\n\n"
        "- TODO\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    sys.exit(main())
