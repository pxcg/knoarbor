from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "specs" / "registry.json"
CORE_FILES = ("requirements.md", "design.md", "tasks.md", "verification.md")
REQUIRED_STANDARDS = (
    "docs/standards/development-workflow.md",
    "docs/standards/spec-driven-development.md",
    "docs/standards/code-navigation-map.md",
)
CAPABILITY_STATES = (
    {"frozen", "defined", "undefined"},
    {"complete", "foundation", "partial", "unimplemented"},
    {"broad", "focused", "mapped", "none"},
    {"scoped_pass", "partial", "pending", "not_applicable"},
)


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
    _check_standards(errors)
    _check_capabilities(errors)
    _check_semantic_hosts(errors)
    _check_skills(errors)
    _check_reference_reuse(errors)
    _check_generated_harness_state(errors)
    _check_retired_harness_authorities(errors)
    if errors:
        print("\n".join(errors))
        return 1
    print("Documentation governance check passed.")
    return 0


def _check_standards(errors: list[str]) -> None:
    for relative in REQUIRED_STANDARDS:
        if not (ROOT / relative).is_file():
            errors.append(f"{relative}: required engineering standard is missing")


def _check_capabilities(errors: list[str]) -> None:
    path = ROOT / "docs" / "CAPABILITY_MAP.md"
    rows = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.match(r"^\| CAP-[A-Z0-9-]+ \|", line)
    ]
    seen: set[str] = set()
    for line in rows:
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 8:
            errors.append(f"docs/CAPABILITY_MAP.md: invalid capability row: {line}")
            continue
        capability_id = cells[0]
        if capability_id in seen:
            errors.append(f"docs/CAPABILITY_MAP.md: duplicate ID {capability_id}")
        seen.add(capability_id)
        for index, allowed in enumerate(CAPABILITY_STATES, start=2):
            if cells[index] not in allowed:
                errors.append(
                    f"docs/CAPABILITY_MAP.md: invalid maturity {cells[index]!r} for {capability_id}"
                )
        owner = re.fullmatch(r"`([^`]+\.md)`", cells[7])
        if not owner or not (ROOT / owner.group(1)).is_file():
            errors.append(
                f"docs/CAPABILITY_MAP.md: invalid active owner for {capability_id}: {cells[7]}"
            )
    if not rows:
        errors.append("docs/CAPABILITY_MAP.md: no machine-readable capability rows")


def _check_semantic_hosts(errors: list[str]) -> None:
    path = ROOT / "harness" / "rules" / "semantic-hosts.json"
    if not path.is_file():
        errors.append("harness/rules/semantic-hosts.json: missing projection")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != "knoarbor.semantic_hosts.v1":
        errors.append("harness/rules/semantic-hosts.json: unsupported schemaVersion")
    if payload.get("authority") != "projection_of_active_contracts":
        errors.append("harness/rules/semantic-hosts.json: must declare projection authority")
    contracts = (ROOT / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
    seen_hosts: set[str] = set()
    seen_responsibilities: set[str] = set()
    for host in payload.get("hosts", []):
        host_id = str(host.get("id", ""))
        if not host_id or host_id in seen_hosts:
            errors.append(f"harness/rules/semantic-hosts.json: duplicate/missing host {host_id!r}")
        seen_hosts.add(host_id)
        module = str(host.get("hostModule", ""))
        owner = str(host.get("ownerDocument", ""))
        if not (ROOT / module).is_file():
            errors.append(f"harness/rules/semantic-hosts.json: missing host module {module}")
        if not (ROOT / owner).is_file():
            errors.append(f"harness/rules/semantic-hosts.json: missing owner document {owner}")
        for value in (host_id, module):
            if value not in contracts:
                errors.append(
                    f"harness/rules/semantic-hosts.json: {value} is not declared by docs/CONTRACTS.md"
                )
        for responsibility in host.get("responsibilities", []):
            responsibility_id = str(responsibility.get("id", ""))
            if not responsibility_id or responsibility_id in seen_responsibilities:
                errors.append(
                    "harness/rules/semantic-hosts.json: duplicate/missing responsibility "
                    f"{responsibility_id!r}"
                )
            seen_responsibilities.add(responsibility_id)
            if responsibility_id not in contracts:
                errors.append(
                    f"harness/rules/semantic-hosts.json: {responsibility_id} is not declared by docs/CONTRACTS.md"
                )


def _check_skills(errors: list[str]) -> None:
    root = ROOT / ".codex" / "skills"
    required = {
        "development-workflow",
        "development-harness-controller",
        "documentation-curation-review",
        "semantic-contract-review",
    }
    existing = {path.parent.name for path in root.glob("*/SKILL.md")}
    for skill_id in sorted(required - existing):
        errors.append(f".codex/skills/{skill_id}/SKILL.md: required Skill is missing")
    for path in root.glob("*/SKILL.md"):
        content = path.read_text(encoding="utf-8")
        match = re.match(
            r"^---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n",
            content,
        )
        if not match or match.group(1) != path.parent.name:
            errors.append(f"{path.relative_to(ROOT)}: invalid Skill metadata")
        if "TODO" in content:
            errors.append(f"{path.relative_to(ROOT)}: unresolved TODO")
        if not (path.parent / "agents" / "openai.yaml").is_file():
            errors.append(f"{path.parent.relative_to(ROOT)}: agents/openai.yaml is missing")


def _check_reference_reuse(errors: list[str]) -> None:
    path = (
        ROOT
        / "specs"
        / "1.41-project-development-harness"
        / "reference-reuse-manifest.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "knoarbor_reference_reuse.v1":
        errors.append(f"{path.relative_to(ROOT)}: unsupported schema_version")
    allowed = {"adopt", "adapt", "reject", "defer"}
    seen: set[str] = set()
    for entry in payload.get("entries", []):
        mechanism = str(entry.get("mechanism", ""))
        if not mechanism or mechanism in seen:
            errors.append(
                f"{path.relative_to(ROOT)}: duplicate or missing mechanism {mechanism!r}"
            )
        seen.add(mechanism)
        if entry.get("decision") not in allowed:
            errors.append(
                f"{path.relative_to(ROOT)}: invalid decision for {mechanism!r}"
            )
        for field in ("target_owner", "verification", "cleanup"):
            if not str(entry.get(field, "")).strip():
                errors.append(
                    f"{path.relative_to(ROOT)}: {mechanism!r} lacks {field}"
                )


def _check_generated_harness_state(errors: list[str]) -> None:
    patterns = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    if ".knoarbor/harness/" not in patterns:
        errors.append(".gitignore: generated Harness state must be ignored")
    if ".codex/initiatives/" in patterns:
        errors.append(".gitignore: retired Initiative state path remains")


def _check_retired_harness_authorities(errors: list[str]) -> None:
    retired = (
        "scripts/project-development-harness.py",
        ".codex/development/methods/v2",
    )
    current_files = [
        ROOT / "docs" / "DOCUMENTATION_GOVERNANCE.md",
        ROOT / "docs" / "MAINTAINERS.md",
        ROOT / "docs" / "TESTING.md",
        ROOT / "specs" / "1.41-project-development-harness" / "requirements.md",
        ROOT / "specs" / "1.41-project-development-harness" / "design.md",
        ROOT / "specs" / "1.41-project-development-harness" / "tasks.md",
        ROOT / "specs" / "1.41-project-development-harness" / "verification.md",
    ]
    for path in current_files:
        content = path.read_text(encoding="utf-8")
        for value in retired:
            if value in content:
                errors.append(
                    f"{path.relative_to(ROOT)}: references retired Harness authority {value}"
                )


if __name__ == "__main__":
    raise SystemExit(main())
