#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PUBLIC_FILES = [
    "README.md",
    "LICENSE",
    "NOTICE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "pyproject.toml",
    "docs/API.md",
    "docs/QUICKSTART.md",
    "docs/DEVELOPMENT.md",
    "scripts/prepare-release.py",
    "scripts/live-release-candidate-smoke.sh",
]
PRIVATE_PATTERNS = [
    "config.yaml",
    "config.local.yaml",
    ".env",
    ".local-dev",
    ".venv",
    ".uv-cache",
    "wiki",
    "knoarbor_logo_asset_kit",
    "docs/slides",
]
TRACKED_ARTIFACT_PATTERNS = [
    "dist/",
    "build/",
    ".local-dev/",
    ".uv-cache/",
    ".venv/",
    "renderer/node_modules/",
    "renderer/dist/",
    "renderer/test-results/",
    "renderer/playwright-report/",
    "renderer/tsconfig.tsbuildinfo",
    ".DS_Store",
    "__pycache__/",
    ".egg-info/",
    "docs/slides/",
]


def main() -> int:
    checks = {
        "branch": current_branch(),
        "dirty_worktree": bool(run(["git", "status", "--porcelain"]).stdout.strip()),
        "required_files": missing_required_files(),
        "tracked_private_paths": tracked_private_paths(),
        "tracked_generated_artifacts": tracked_generated_artifacts(),
        "latest_tag": latest_tag(),
        "head": run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip(),
    }
    ok = (
        checks["branch"] in {"main", "dev"}
        and not checks["dirty_worktree"]
        and not checks["required_files"]
        and not checks["tracked_private_paths"]
        and not checks["tracked_generated_artifacts"]
    )
    report = {
        "schema_version": "release_readiness.v1",
        "ready": ok,
        "checks": checks,
        "notes": [
            "Run scripts/dev-check.sh before tagging a release.",
            "Release tags must be created from main only.",
            "This readiness check does not call external model providers.",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def current_branch() -> str:
    return run(["git", "branch", "--show-current"]).stdout.strip()


def latest_tag() -> str | None:
    result = run(["git", "describe", "--tags", "--abbrev=0"])
    return result.stdout.strip() or None


def missing_required_files() -> list[str]:
    return [path for path in REQUIRED_PUBLIC_FILES if not (ROOT / path).exists()]


def tracked_private_paths() -> list[str]:
    tracked = run(["git", "ls-files"]).stdout.splitlines()
    findings: list[str] = []
    for path in tracked:
        first = path.split("/", 1)[0]
        if first in PRIVATE_PATTERNS or path in PRIVATE_PATTERNS:
            findings.append(path)
    return findings


def tracked_generated_artifacts() -> list[str]:
    tracked = run(["git", "ls-files"]).stdout.splitlines()
    findings: list[str] = []
    for path in tracked:
        if any(pattern in path or path.startswith(pattern) for pattern in TRACKED_ARTIFACT_PATTERNS):
            findings.append(path)
    return findings


if __name__ == "__main__":
    sys.exit(main())
