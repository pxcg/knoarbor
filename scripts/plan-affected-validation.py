#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from collections import defaultdict, deque
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3}


def main() -> int:
    args = _parse_args()
    changed = _scoped_paths(args.paths) if args.paths else _changed_files(args.base)
    deleted = [path for path in changed if not (ROOT / path).exists()] if args.paths else _deleted_files(args.base)
    plan = build_plan(changed, deleted_files=deleted)
    if args.allow_empty_tests:
        plan["empty_test_override_reason"] = args.allow_empty_tests
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.run:
        if not plan["mechanical_test_selection_complete"] and not args.allow_empty_tests:
            print(
                "Refusing to run an unresolved Python validation closure. "
                "Add focused tests or pass --allow-empty-tests 'REASON'.",
                file=sys.stderr,
            )
            return 2
        for command in plan["commands"]:
            result = subprocess.run(command, cwd=ROOT, check=False)
            if result.returncode:
                return result.returncode
    return 0


def build_plan(
    changed_files: list[str],
    *,
    deleted_files: list[str] | None = None,
    root: Path = ROOT,
) -> dict[str, object]:
    files = sorted(set(changed_files))
    deleted = set(deleted_files or [])
    readable_files = [path for path in files if path not in deleted]
    commands: list[list[str]] = []
    reasons: list[str] = []
    risk = "R1"

    python_files = [path for path in readable_files if path.endswith(".py")]
    backend_files = [path for path in files if path.startswith(("src/knoarbor/", "tests/", "scripts/")) and path.endswith(".py")]
    renderer_files = [path for path in files if path.startswith("renderer/")]
    desktop_files = [path for path in files if path.startswith("desktop/")]
    docs_files = [path for path in files if path.startswith(("docs/", "specs/"))]

    if python_files:
        commands.append(["uv", "run", "--extra", "dev", "ruff", "check", *python_files])
    if (
        backend_files or any(path.startswith(("renderer/src/", "desktop/src/")) for path in files)
    ) and (root / "scripts/check-architecture.py").exists():
        commands.append(["uv", "run", "python", "scripts/check-architecture.py"])
    if any(path.startswith("src/knoarbor/") for path in files):
        risk = _raise_risk(risk, "R2")
    if renderer_files:
        commands.append(["npm", "--prefix", "renderer", "run", "typecheck"])
        if any(path.startswith("renderer/src/i18n/") for path in renderer_files):
            commands.append(["npm", "--prefix", "renderer", "run", "check:i18n"])
        risk = _raise_risk(risk, "R2" if any(_renderer_shared(path) for path in renderer_files) else "R1")
    if desktop_files:
        commands.append(["npm", "--prefix", "desktop", "run", "typecheck"])
        risk = _raise_risk(risk, "R2")
    if docs_files:
        commands.extend(
            [
                ["uv", "run", "python", "scripts/check-doc-governance.py"],
                ["uv", "run", "python", "scripts/check-doc-links.py"],
            ]
        )

    changed_test_modules = [
        Path(path).with_suffix("").as_posix().replace("/", ".")
        for path in files
        if path not in deleted and path.startswith("tests/test_") and path.endswith(".py")
    ]
    python_closure = _python_dependency_closure(files, deleted, root=root)
    test_modules = sorted(set(changed_test_modules) | set(python_closure["focused_tests"]))
    if test_modules:
        commands.append(["uv", "run", "python", "-m", "unittest", *test_modules])

    if any(_is_r3_path(path) for path in files):
        risk = "R3"
    test_selection_complete = not python_closure["changed_modules"] or bool(test_modules)
    if python_closure["changed_modules"] and not test_modules:
        reasons.append(
            "No focused Python tests were resolved from the owner and reverse-import closure; "
            "add owner coverage or review with --allow-empty-tests."
        )
    if renderer_files:
        reasons.append("Add focused UI interaction coverage only for behavior changed beyond TypeScript contracts.")
    if any(_is_packaging_path(path) for path in files):
        reasons.append("Desktop packaging or release lifecycle is affected; use the project desktop-lifecycle skill before any build/install/package action.")
    if any(_is_release_governance_path(path) for path in files):
        reasons.append("Test or release governance is affected; validate the focused script/validator contract and review CI or release checkpoint propagation.")

    return {
        "changed_files": files,
        "deleted_files": sorted(deleted),
        "risk_floor": risk,
        "mechanical_test_selection_complete": test_selection_complete,
        "python_closure": python_closure,
        "commands": _deduplicate_commands(commands),
        "review_required": reasons,
        "note": (
            "Risk remains a path-based floor and the Python import graph is a static mechanical closure. "
            "Review semantic, persisted, runtime, renderer, desktop, and release dependencies explicitly."
        ),
    }


def _python_dependency_closure(files: list[str], deleted: set[str], *, root: Path) -> dict[str, list[str]]:
    module_paths = _discover_python_modules(root)
    known_modules = set(module_paths)
    reverse_dependencies: dict[str, set[str]] = defaultdict(set)

    for importer, path in module_paths.items():
        for dependency in _read_imports(path, importer, known_modules):
            reverse_dependencies[dependency].add(importer)

    changed_modules = {
        module
        for path in files
        if path.startswith("src/knoarbor/") and path.endswith(".py")
        if (module := _module_name(Path(path))) is not None
    }
    affected = set(changed_modules)
    queue = deque(changed_modules)
    while queue:
        for importer in reverse_dependencies.get(queue.popleft(), set()):
            if importer not in affected:
                affected.add(importer)
                queue.append(importer)

    focused_tests = {
        module
        for module in affected
        if (path := module_paths.get(module)) is not None and _is_test_path(path, root)
    }
    for path in files:
        if path in deleted or not path.startswith("src/knoarbor/") or not path.endswith(".py"):
            continue
        owner_test = root / "tests" / f"test_{Path(path).stem}.py"
        if owner_test.exists():
            focused_tests.add(f"tests.test_{Path(path).stem}")

    return {
        "changed_modules": sorted(changed_modules),
        "affected_modules": sorted(affected - changed_modules),
        "focused_tests": sorted(focused_tests),
    }


def _discover_python_modules(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for base in (root / "src" / "knoarbor", root / "tests"):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            module = _module_name(path.relative_to(root))
            if module:
                result[module] = path
    return result


def _module_name(path: Path) -> str | None:
    parts = list(path.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or None


def _read_imports(path: Path, importer: str, known_modules: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    dependencies: set[str] = set()
    package = importer if path.name == "__init__.py" else importer.rpartition(".")[0]
    for node in ast.walk(tree):
        candidates: set[str] = set()
        if isinstance(node, ast.Import):
            candidates.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_import_from(package, node.module, node.level)
            if base:
                candidates.add(base)
                candidates.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
        for candidate in candidates:
            if candidate in known_modules:
                dependencies.add(candidate)
            parts = candidate.split(".")
            for index in range(1, len(parts)):
                parent = ".".join(parts[:index])
                if parent in known_modules:
                    dependencies.add(parent)
    return dependencies


def _resolve_import_from(package: str, module: str | None, level: int) -> str:
    if not level:
        return module or ""
    package_parts = package.split(".") if package else []
    keep = max(0, len(package_parts) - level + 1)
    parts = package_parts[:keep]
    if module:
        parts.extend(module.split("."))
    return ".".join(parts)


def _is_test_path(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return len(relative.parts) >= 2 and relative.parts[0] == "tests" and relative.name.startswith("test_")


def _changed_files(base: str | None) -> list[str]:
    commands = [["diff", "--name-only", f"{base}...HEAD"]] if base else [["diff", "--name-only", "HEAD"]]
    commands.append(["ls-files", "--others", "--exclude-standard"])
    result: set[str] = set()
    for command in commands:
        output = subprocess.check_output(["git", *command], cwd=ROOT, text=True)
        result.update(line.strip() for line in output.splitlines() if line.strip())
    return sorted(result)


def _deleted_files(base: str | None) -> list[str]:
    range_arg = f"{base}...HEAD" if base else "HEAD"
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=D", range_arg],
        cwd=ROOT,
        text=True,
    )
    return sorted(line.strip() for line in output.splitlines() if line.strip())


def _raise_risk(current: str, candidate: str) -> str:
    return candidate if RISK_ORDER[candidate] > RISK_ORDER[current] else current


def _renderer_shared(path: str) -> bool:
    return path.startswith(("renderer/src/api/", "renderer/src/appContext.ts", "renderer/src/components/", "renderer/src/desktop/"))


def _is_r3_path(path: str) -> bool:
    return path.startswith(
        (
            "src/knoarbor/core/schemas/",
            "src/knoarbor/runtime/",
            "src/knoarbor/storage/",
            "src/knoarbor/migrations/",
        )
    ) or _is_packaging_path(path) or _is_release_governance_path(path)


def _is_packaging_path(path: str) -> bool:
    return path.startswith(("desktop/electron-builder", "desktop/scripts/build-service", "desktop/scripts/clean-package", "desktop/resources/"))


def _is_release_governance_path(path: str) -> bool:
    return path.startswith(
        (
            ".github/workflows/",
            ".codex/skills/knoarbor-full-chain-acceptance/",
            ".codex/skills/knoarbor-sdd-delivery/",
            ".codex/skills/development-harness-controller/",
            ".codex/skills/development-workflow/",
            "harness/",
            "specs/1.41-project-development-harness/",
        )
    ) or path in {
        ".github/pull_request_template.md",
        "pnpm-workspace.yaml",
        "scripts/bootstrap-development-harness.mjs",
        "scripts/check-doc-governance.py",
        "scripts/dev-check.sh",
        "scripts/release-check.sh",
        "scripts/release-readiness.py",
        "scripts/clean-clone-smoke.sh",
        "scripts/live-release-candidate-smoke.sh",
    }


def _deduplicate_commands(commands: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, ...]] = set()
    result: list[list[str]] = []
    for command in commands:
        key = tuple(command)
        if key not in seen:
            seen.add(key)
            result.append(command)
    return result


def _scoped_paths(paths: list[str]) -> list[str]:
    result: set[str] = set()
    for value in paths:
        path = Path(value)
        candidate = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
        try:
            normalized = candidate.relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise SystemExit(f"Scoped path is outside the repository: {value}") from exc
        if not normalized or normalized == "." or normalized.startswith("../"):
            raise SystemExit(f"Invalid scoped path: {value}")
        result.add(normalized)
    return sorted(result)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan minimum validation for the current changed-file set.")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--base", help="Git base used for committed changes (base...HEAD).")
    scope.add_argument("--paths", nargs="+", metavar="PATH", help="Plan only the explicitly listed repository-relative task paths.")
    parser.add_argument("--run", action="store_true", help="Run only the mechanically selected commands after printing the plan.")
    parser.add_argument(
        "--allow-empty-tests",
        metavar="REASON",
        help="Allow --run without resolved focused tests and record the explicit review reason.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
