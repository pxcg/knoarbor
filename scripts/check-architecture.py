#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "src" / "knoarbor"
RENDERER_ROOT = ROOT / "renderer" / "src"

FORBIDDEN_IMPORTS = {
    "core": {"knoarbor.entrypoints", "knoarbor.cli_commands", "knoarbor.services", "knoarbor.pipelines"},
    "runtime": {"knoarbor.entrypoints", "knoarbor.cli_commands", "knoarbor.services"},
    "storage": {"knoarbor.entrypoints", "knoarbor.cli_commands", "knoarbor.services", "knoarbor.pipelines"},
    "pipelines": {"knoarbor.entrypoints", "knoarbor.cli_commands", "knoarbor.services"},
}


def main() -> int:
    errors = [
        *_check_import_direction(),
        *_check_import_cycles(),
        *_check_backend_composition_surfaces(),
        *_check_chat_boundaries(),
        *_check_renderer_direction(),
    ]
    if errors:
        print("Architecture governance failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Architecture governance passed: backend and renderer dependency directions are valid.")
    return 0


def _check_import_direction() -> list[str]:
    errors: list[str] = []
    for path in PYTHON_ROOT.rglob("*.py"):
        relative = path.relative_to(PYTHON_ROOT)
        owner = relative.parts[0]
        forbidden = FORBIDDEN_IMPORTS.get(owner)
        if not forbidden:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                blocked = next((prefix for prefix in forbidden if module == prefix or module.startswith(prefix + ".")), None)
                if blocked:
                    errors.append(f"{relative}:{node.lineno} imports forbidden higher layer {module}")
    return errors


def _check_import_cycles(root: Path = PYTHON_ROOT) -> list[str]:
    modules = {_module_name(path, root): path for path in root.rglob("*.py")}
    graph = {
        module: _runtime_module_imports(path, module, modules)
        for module, path in modules.items()
    }
    return [
        f"backend import cycle: {' | '.join(component)}"
        for component in _strongly_connected_components(graph)
        if len(component) > 1
    ]


def _check_backend_composition_surfaces(root: Path = PYTHON_ROOT) -> list[str]:
    modules = {_module_name(path, root): path for path in root.rglob("*.py")}
    storage_root = root / "storage" / "__init__.py"
    if not storage_root.exists():
        return []
    module = _module_name(storage_root, root)
    return [
        (
            f"{storage_root.relative_to(root)} eagerly imports {dependency}; "
            "storage package root must remain composition-free"
        )
        for dependency in sorted(_runtime_module_imports(storage_root, module, modules))
    ]


def _module_name(path: Path, root: Path) -> str:
    parts = path.relative_to(root).with_suffix("").parts
    module = ".".join((root.name, *parts))
    return module.removesuffix(".__init__")


def _runtime_module_imports(
    path: Path,
    module: str,
    modules: dict[str, Path],
) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    imports: set[str] = set()

    class RuntimeImportVisitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            if _is_type_checking_guard(node.test):
                for statement in node.orelse:
                    self.visit(statement)
                return
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                if alias.name in modules and alias.name != module:
                    imports.add(alias.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            base = _resolved_import_base(package, node.module, node.level)
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                target = candidate if candidate in modules else base
                if target in modules and target != module:
                    imports.add(target)

    RuntimeImportVisitor().visit(tree)
    return imports


def _is_type_checking_guard(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id == "TYPE_CHECKING"
    ) or (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
        and node.attr == "TYPE_CHECKING"
    )


def _resolved_import_base(package: str, module: str | None, level: int) -> str:
    if level == 0:
        return module or ""
    parts = package.split(".")
    keep = max(0, len(parts) - (level - 1))
    prefix = ".".join(parts[:keep])
    return ".".join(part for part in (prefix, module or "") if part)


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(module: str) -> None:
        nonlocal index
        indexes[module] = index
        lowlinks[module] = index
        index += 1
        stack.append(module)
        on_stack.add(module)
        for dependency in graph[module]:
            if dependency not in indexes:
                visit(dependency)
                lowlinks[module] = min(lowlinks[module], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[module] = min(lowlinks[module], indexes[dependency])
        if lowlinks[module] != indexes[module]:
            return
        component: list[str] = []
        while stack:
            candidate = stack.pop()
            on_stack.remove(candidate)
            component.append(candidate)
            if candidate == module:
                break
        components.append(sorted(component))

    for module in sorted(graph):
        if module not in indexes:
            visit(module)
    return components


def _check_chat_boundaries(services_root: Path | None = None) -> list[str]:
    root = services_root or PYTHON_ROOT / "services"
    errors: list[str] = []
    merge_owners: list[Path] = []
    for path in root.glob("chat*.py"):
        source = path.read_text(encoding="utf-8")
        if "ApplicationServices" in source:
            errors.append(f"{path.relative_to(root.parent)} depends on the full application service container")
        tree = ast.parse(source, filename=str(path))
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"merge_messages", "_merge_messages"}
            for node in ast.walk(tree)
        ):
            merge_owners.append(path)
    expected_owner = root / "chat_messages.py"
    if merge_owners != [expected_owner]:
        owners = ", ".join(str(path.relative_to(root.parent)) for path in merge_owners) or "none"
        errors.append(f"chat message merge must be owned only by services/chat_messages.py; found {owners}")
    return errors


def _check_renderer_direction(renderer_root: Path = RENDERER_ROOT) -> list[str]:
    errors: list[str] = []
    api_sources = [
        *(renderer_root / "api" / "contracts").glob("*.ts"),
        *(renderer_root / "api").glob("*.ts"),
    ]
    for path in api_sources:
        if path.name == "client.ts":
            invalid = [
                (line_number, line)
                for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
                if line.strip()
                and not line.lstrip().startswith("//")
                and not re.fullmatch(
                    r"export (?:type )?(?:\*|\{[^}]*\}) from [\"'][^\"']+[\"'];",
                    line.strip(),
                )
            ]
            for line_number, _line in invalid:
                errors.append(f"{_display_path(path)}:{line_number} implements behavior in the API composition surface")
            continue
        if 'from "./client"' in path.read_text(encoding="utf-8") or "from './client'" in path.read_text(encoding="utf-8"):
            errors.append(f"{_display_path(path)} imports the API composition surface")
    for path in (renderer_root / "i18n" / "locales").glob("*.ts"):
        source = path.read_text(encoding="utf-8")
        if 'from "../data"' in source or "from '../data'" in source:
            errors.append(f"{_display_path(path)} imports the locale composition surface")
    for owner in ("pages", "components", "ingest"):
        for path in (renderer_root / owner).rglob("*.ts*"):
            source = path.read_text(encoding="utf-8")
            if re.search(
                r"import(?:\s+type)?\s*\{[^}]*\bAppContext\b[^}]*\}\s*from\s*[\"'][^\"']*appContext[\"']",
                source,
                flags=re.DOTALL,
            ):
                errors.append(f"{_display_path(path)} depends on the full application context")
    routes = renderer_root / "appRoutes.tsx"
    if routes.exists() and re.search(
        r"\bcontext\s*=\s*\{\s*context\s*\}",
        routes.read_text(encoding="utf-8"),
    ):
        errors.append(
            f"{_display_path(routes)} passes the full application context to a route page; "
            "project the page capability slice first"
        )
    duplicate_contract_markers = {
        renderer_root / "vite-env.d.ts": ("type KnoArborDesktopBridge", "type DesktopUpdateState"),
        renderer_root / "desktop" / "desktopBridge.ts": ("type DesktopEnvironment", "type DesktopPickerResult"),
    }
    for path, markers in duplicate_contract_markers.items():
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker in source:
                errors.append(f"{_display_path(path)} duplicates desktop IPC contract {marker.removeprefix('type ')}")
    return errors


def _display_path(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


if __name__ == "__main__":
    sys.exit(main())
