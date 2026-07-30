from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Callable, Iterator, Sequence
from urllib.parse import urlparse


METHOD_SCHEMA = "knoarbor_development_method.v2"
RUN_SCHEMA = "knoarbor_development_initiative.v2"
POINTER_SCHEMA = "knoarbor_development_method_pointer.v1"
METHOD_JSON_FILES = (
    "workflow.json",
    "roles.json",
    "artifacts.json",
    "gates.json",
    "project-map.json",
    "delivery.json",
)
METHOD_TEXT_FILES = ("policy.md", "controller.md")
DERIVED_VIEWS = ("artifacts", "baseline", "gates", "decisions", "delivery", "metrics", "handoff")
RESOLVED = {"passed", "skipped"}
CANONICAL_STAGES = (
    "initialization", "requirement_analysis", "requirement_confirmation", "current_state_evidence", "design",
    "design_confirmation", "independent_design_review", "workspace_baseline", "implementation", "integration",
    "independent_code_review", "acceptance", "closure",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*\S+", re.IGNORECASE),
)
CANARY_PATH_PATTERN = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^\s:]+")
ABSOLUTE_PRIVATE_PATTERN = re.compile(r"(?:^|\s)(?:/(?!/)[^\s]+|[A-Za-z]:\\[^\s]+)")
GATE_PRIVATE_PATH_PATTERN = re.compile(
    r"(?<!<repo>)(?<![A-Za-z0-9_</])(?:/(?!/)[^\s\"']+|[A-Za-z]:\\[^\s\"']+)"
)
DIAGNOSTIC_FILE_PATTERN = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.(?:py|ts|tsx|md|json))(?::\d+(?::\d+)?|\(\d+,\d+\))?")
DIAGNOSTIC_LINE_PATTERNS = (
    re.compile(r"^(?:FAIL|ERROR):\s"),
    re.compile(r"^(?:FAILED|ERROR)\s"),
    re.compile(r"^E\s+"),
    re.compile(r"\b(?:AssertionError|[A-Za-z][A-Za-z0-9_]*(?:Error|Exception))(?::|$)"),
    re.compile(r"\berror\s+TS\d+:", re.IGNORECASE),
    re.compile(r"\b[A-Z]\d{3,4}\b"),
)
VOLATILE_OUTPUT_PATTERNS = (
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"), "<timestamp>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ ]\d{2}:\d{2}:\d{2}(?:\.\d+)?\b"), "<timestamp>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE), "<uuid>"),
    (re.compile(r"\b(?:run|task|job)[_-]?id\s*[:=]\s*[A-Za-z0-9._:-]+", re.IGNORECASE), "<execution-id>"),
    (re.compile(r"(?<!\d)(?:localhost|<env>host|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}\b"), "<endpoint>"),
    (re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|s|sec(?:onds?)?)\b", re.IGNORECASE), "<duration>"),
)


class HarnessError(ValueError):
    pass


@dataclass(frozen=True)
class Method:
    version: str
    relative_path: str
    path: Path
    digests: dict[str, str]
    workflow: dict[str, Any]
    roles: dict[str, Any]
    artifacts: dict[str, Any]
    gates: dict[str, Any]
    project_map: dict[str, Any]
    delivery: dict[str, Any]
    texts: dict[str, str]

    @property
    def stages(self) -> list[str]:
        return [item["id"] for item in self.workflow["stages"]]

    def stage(self, stage_id: str) -> dict[str, Any]:
        try:
            return next(item for item in self.workflow["stages"] if item["id"] == stage_id)
        except StopIteration as exc:
            raise HarnessError(f"unknown stage: {stage_id}") from exc

    def role(self, role_id: str) -> dict[str, Any]:
        try:
            return next(item for item in self.roles["roles"] if item["id"] == role_id)
        except StopIteration as exc:
            raise HarnessError(f"unknown role: {role_id}") from exc

    def artifact(self, kind: str) -> dict[str, Any]:
        try:
            return next(item for item in self.artifacts["artifacts"] if item["id"] == kind)
        except StopIteration as exc:
            raise HarnessError(f"unknown artifact kind: {kind}") from exc

    def gate(self, gate_id: str) -> dict[str, Any]:
        try:
            return next(item for item in self.gates["gates"] if item["id"] == gate_id)
        except StopIteration as exc:
            raise HarnessError(f"unknown gate: {gate_id}") from exc


def now() -> str:
    return datetime.now(UTC).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(canonical(value))


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"invalid JSON record: {path.name}") from exc
    if not isinstance(value, dict):
        raise HarnessError(f"JSON record must be an object: {path.name}")
    return value


def reject_secrets(value: Any, location: str = "record") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            reject_secrets(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_secrets(item, f"{location}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_PATTERNS):
        raise HarnessError(f"credential-like content is forbidden in {location}")


def bounded_text(value: Any, location: str, *, maximum: int = 240, token: bool = False) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\n" in value or "\r" in value:
        raise HarnessError(f"{location} must be bounded single-line text")
    if ABSOLUTE_PRIVATE_PATTERN.search(value):
        raise HarnessError(f"private absolute path is forbidden in {location}")
    if token and not re.fullmatch(r"[A-Za-z0-9._:-]+", value):
        raise HarnessError(f"{location} must be a stable token")
    reject_secrets(value, location)
    return value


def reject_private_paths(value: Any, location: str = "record") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            reject_private_paths(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_private_paths(item, f"{location}[{index}]")
    elif isinstance(value, str) and ABSOLUTE_PRIVATE_PATTERN.search(value):
        raise HarnessError(f"private absolute path is forbidden in {location}")


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    reject_secrets(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _unique(records: list[dict[str, Any]], field: str, asset: str) -> set[str]:
    values = [item.get(field) for item in records]
    if any(not isinstance(item, str) or not item for item in values):
        raise HarnessError(f"{asset} contains an invalid {field}")
    if len(values) != len(set(values)):
        raise HarnessError(f"{asset} contains duplicate {field} values")
    return set(values)


def load_method(root: Path, relative_path: str | None = None) -> Method:
    root = root.resolve()
    if relative_path is None:
        pointer = read_json(root / ".codex" / "development" / "current.json")
        if pointer.get("schema_version") != POINTER_SCHEMA:
            raise HarnessError("unsupported development method pointer")
        relative_path = str(pointer.get("path", ""))
        version = str(pointer.get("method_version", ""))
    else:
        version = Path(relative_path).name
    method_path = (root / relative_path).resolve()
    try:
        method_path.relative_to(root)
    except ValueError as exc:
        raise HarnessError("method path is outside the repository") from exc
    records: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    digests: dict[str, str] = {}
    for name in (*METHOD_TEXT_FILES, *METHOD_JSON_FILES):
        path = method_path / name
        if not path.is_file():
            raise HarnessError(f"method bundle is missing {name}")
        payload = path.read_bytes()
        digests[name] = digest_bytes(payload)
        if name.endswith(".json"):
            record = read_json(path)
            if record.get("schema_version") != METHOD_SCHEMA:
                raise HarnessError(f"unsupported method asset schema: {name}")
            records[name] = record
        else:
            texts[name] = payload.decode("utf-8")
    method = Method(
        version=version,
        relative_path=Path(relative_path).as_posix(),
        path=method_path,
        digests=digests,
        workflow=records["workflow.json"],
        roles=records["roles.json"],
        artifacts=records["artifacts.json"],
        gates=records["gates.json"],
        project_map=records["project-map.json"],
        delivery=records["delivery.json"],
        texts=texts,
    )
    try:
        validate_method(method)
    except HarnessError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise HarnessError("development method bundle is malformed") from exc
    return method


def validate_method(method: Method) -> None:
    stages = _unique(method.workflow.get("stages", []), "id", "workflow")
    roles = _unique(method.roles.get("roles", []), "id", "roles")
    artifacts = _unique(method.artifacts.get("artifacts", []), "id", "artifacts")
    gates = _unique(method.gates.get("gates", []), "id", "gates")
    adapters = _unique(method.delivery.get("adapters", []), "id", "delivery")
    if tuple(method.stages) != CANONICAL_STAGES:
        raise HarnessError("workflow must contain the canonical thirteen stages")
    if roles != {"controller", "requirement", "design", "implementer", "reviewer"}:
        raise HarnessError("method must contain the canonical five roles")
    if gates != {"affected-validation", "artifact-consistency", "secret-scan", "development-suite", "full-chain-focused", "renderer-interaction", "desktop-contracts", "live-model-local-observation", "live-model-release"}:
        raise HarnessError("method gate catalog is not canonical")
    expected_assets = {name: Path(name).stem for name in METHOD_JSON_FILES}
    for name, asset in expected_assets.items():
        record = {"workflow.json": method.workflow, "roles.json": method.roles, "artifacts.json": method.artifacts, "gates.json": method.gates, "project-map.json": method.project_map, "delivery.json": method.delivery}[name]
        if record.get("asset") != asset:
            raise HarnessError(f"method asset identity is invalid: {name}")
    required_headings = {"policy.md": ("## Authority", "## Invariants", "## Completion"), "controller.md": ("## Admission", "## Relay", "## Deterministic Boundaries", "## Delivery And Closure")}
    for name, headings in required_headings.items():
        if any(heading not in method.texts[name] for heading in headings):
            raise HarnessError(f"method text contract is incomplete: {name}")
    for stage in method.workflow["stages"]:
        if stage.get("owner") not in roles:
            raise HarnessError(f"stage references unknown role: {stage['id']}")
        if any(target not in stages for target in stage.get("rollback", [])):
            raise HarnessError(f"stage has an unknown rollback target: {stage['id']}")
        if any(route not in {"fast", "standard", "strict"} for route in stage.get("required_by", [])):
            raise HarnessError(f"stage has an invalid required route: {stage['id']}")
        if any(value not in {"fast_route", "not_bugfix", "existing_equivalent_evidence", "no_public_or_cross_owner_change"} for value in stage.get("skip_types", [])):
            raise HarnessError(f"stage has an invalid skip type: {stage['id']}")
    for artifact in method.artifacts["artifacts"]:
        if artifact.get("stage") not in stages or artifact.get("producer") not in roles:
            raise HarnessError(f"artifact has an unknown stage or producer: {artifact['id']}")
        if artifact.get("storage_class") not in {"repository_ref", "control_record"}:
            raise HarnessError(f"artifact has invalid storage_class: {artifact['id']}")
        success_outcomes = artifact.get("success_outcomes")
        if artifact.get("storage_class") == "control_record" and (
            not isinstance(success_outcomes, list)
            or not success_outcomes
            or any(outcome not in {"approved", "passed", "delivered"} for outcome in success_outcomes)
        ):
            raise HarnessError(f"control artifact lacks valid success_outcomes: {artifact['id']}")
        producer = method.role(artifact["producer"])
        if artifact["id"] not in producer.get("write_kinds", []):
            raise HarnessError(f"artifact producer role cannot write kind: {artifact['id']}")
    for stage, kinds in method.artifacts.get("required_outputs", {}).items():
        if stage not in stages or any(kind not in artifacts for kind in kinds):
            raise HarnessError(f"required_outputs has an unknown reference: {stage}")
        if any(method.artifact(kind)["stage"] != stage for kind in kinds):
            raise HarnessError(f"required_outputs crosses stage ownership: {stage}")
    for role in method.roles["roles"]:
        if any(kind != "*" and kind not in artifacts for kind in role.get("read_kinds", [])):
            raise HarnessError(f"role has an unknown read artifact: {role['id']}")
        if any(kind not in artifacts for kind in role.get("write_kinds", [])):
            raise HarnessError(f"role has an unknown write artifact: {role['id']}")
    for profile, selected in method.gates.get("profiles", {}).items():
        if profile not in {"fast", "standard", "strict"} or any(gate not in gates for gate in selected):
            raise HarnessError(f"gate profile has an unknown reference: {profile}")
    for gate in method.gates["gates"]:
        if gate.get("severity") not in {"hard", "soft"}:
            raise HarnessError(f"gate has invalid severity: {gate['id']}")
        if gate.get("executor") not in {"command", "internal_secret_scan", "external_acceptance"}:
            raise HarnessError(f"gate has invalid executor: {gate['id']}")
        if gate.get("executor") == "command" and not isinstance(gate.get("command"), list):
            raise HarnessError(f"command gate lacks an argument array: {gate['id']}")
        if any(phase not in {"baseline", "integration", "acceptance"} for phase in gate.get("phases", [])):
            raise HarnessError(f"gate has an invalid phase: {gate['id']}")
        if gate.get("condition") not in {"always", "explicit", "release", "renderer_scope", "desktop_scope"}:
            raise HarnessError(f"gate has an invalid condition: {gate['id']}")
    if adapters != {"local", "github"}:
        raise HarnessError("v2 delivery adapters must be local and github")
    side_effects = set(method.delivery.get("side_effect_classes", []))
    for adapter in method.delivery["adapters"]:
        authorization = adapter.get("required_authorization")
        if authorization is not None and authorization not in side_effects:
            raise HarnessError(f"delivery adapter has unknown authorization: {adapter['id']}")
    for owner in method.project_map.get("owners", []):
        if not all(isinstance(owner.get(field), expected) for field, expected in {"prefix": str, "owner": str, "specs": list, "tests": list, "skill": str}.items()):
            raise HarnessError("project map owner is malformed")


def normalized_https_url(value: Any, location: str) -> str:
    text = bounded_text(value, location, maximum=500)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HarnessError(f"{location} must be a normalized HTTPS URL")
    return text


def normalized_paths(values: Sequence[str], root: Path) -> list[str]:
    result: set[str] = set()
    for value in values:
        prefix = value.endswith("/")
        raw = value[:-1] if prefix else value
        resolved = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        try:
            relative = resolved.relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise HarnessError(f"path is outside the repository: {value}") from exc
        if not relative or relative == "." or ".." in Path(relative).parts:
            raise HarnessError(f"invalid repository path: {value}")
        result.add(relative + ("/" if prefix else ""))
    if not result:
        raise HarnessError("at least one allowed path is required")
    return sorted(result)


def path_allowed(path: str, allowed: Sequence[str]) -> bool:
    return any(path.startswith(rule) if rule.endswith("/") else path == rule for rule in allowed)


def run_directory(runs_root: Path, initiative_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,79}", initiative_id):
        raise HarnessError("initiative ID must be 3-80 lowercase characters")
    return runs_root / initiative_id


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(["git", *arguments], cwd=root, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise HarnessError(f"git command failed: {' '.join(arguments)}")
    return result.stdout.strip()


def repository_fingerprints(root: Path, runs_root: Path) -> dict[str, str]:
    output = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    try:
        runs_prefix = runs_root.resolve().relative_to(root.resolve()).as_posix().rstrip("/") + "/"
    except ValueError:
        runs_prefix = ""
    result: dict[str, str] = {}
    for value in output.split("\0"):
        if not value or (runs_prefix and value.startswith(runs_prefix)):
            continue
        path = root / value
        if path.is_symlink():
            payload = f"symlink:{path.readlink()}".encode()
        elif path.is_file():
            payload = path.read_bytes()
        else:
            payload = b"missing"
        result[value] = digest_bytes(payload)
    return dict(sorted(result.items()))


def create_initiative(
    *,
    root: Path,
    runs_root: Path,
    initiative_id: str,
    title: str,
    route: str,
    spec: str,
    objective_ref: str,
    non_goals: list[str],
    allowed_paths: list[str],
    roles: dict[str, str],
    budgets: dict[str, int],
    side_effects: list[str],
    extra_gates: list[str] | None = None,
) -> Path:
    method = load_method(root)
    if route not in method.gates["profiles"]:
        raise HarnessError(f"unknown route: {route}")
    run_dir = run_directory(runs_root, initiative_id)
    if run_dir.exists():
        raise HarnessError(f"initiative already exists: {initiative_id}")
    role_ids = {item["id"] for item in method.roles["roles"]}
    if set(roles) != role_ids or any(not value for value in roles.values()):
        raise HarnessError("all method role execution IDs are required")
    for role, execution_id in roles.items():
        bounded_text(execution_id, f"roles.{role}", maximum=160)
    if route in {"standard", "strict"} and roles["implementer"] == roles["reviewer"]:
        raise HarnessError("implementer and reviewer execution IDs must differ")
    if budgets.get("max_depth") != 1 or budgets.get("max_parallel_children") != 1:
        raise HarnessError("v2 fixes Agent depth and parallel children at one")
    if any(not isinstance(budgets.get(name), int) or budgets[name] < 0 for name in ("max_agent_calls", "max_retries_per_stage")):
        raise HarnessError("call and retry budgets must be non-negative integers")
    allowed = normalized_paths(allowed_paths, root)
    objective = normalized_paths([objective_ref], root)[0]
    spec_path = normalized_paths([spec], root)[0]
    if not (root / objective).is_file():
        raise HarnessError("objective reference must be an existing repository file")
    bounded_text(title, "title", maximum=160)
    if len(non_goals) > 20:
        raise HarnessError("too many non-goals")
    for index, value in enumerate(non_goals):
        bounded_text(value, f"non_goals[{index}]")
    gate_ids = list(method.gates["profiles"][route])
    for gate_id in extra_gates or []:
        method.gate(gate_id)
        if gate_id not in gate_ids:
            gate_ids.append(gate_id)
    effective_gates = [deepcopy(method.gate(gate_id)) for gate_id in gate_ids]
    permitted_effects = set(method.delivery.get("side_effect_classes", []))
    if any(effect not in permitted_effects for effect in side_effects):
        raise HarnessError("unknown side-effect authorization")
    manifest = {
        "schema_version": RUN_SCHEMA,
        "initiative_id": initiative_id,
        "title": title,
        "route": route,
        "spec": spec_path,
        "objective_ref": objective,
        "non_goals": non_goals,
        "allowed_paths": allowed,
        "roles": roles,
        "budgets": budgets,
        "authorized_side_effects": sorted(set(side_effects)),
        "method": {"version": method.version, "path": method.relative_path, "digests": method.digests},
        "effective_gates": effective_gates,
        "created_at": now(),
    }
    reject_secrets(manifest)
    stages = {
        stage: {
            "status": "passed" if stage == "initialization" else "pending",
            "attempt": 1 if stage == "initialization" else 0,
            "actor": roles["controller"] if stage == "initialization" else None,
            "entered_at": manifest["created_at"] if stage == "initialization" else None,
            "resolved_at": manifest["created_at"] if stage == "initialization" else None,
            "reason": None,
            "skip_type": None,
            "artifact_ids": [],
            "rollback_source": None,
        }
        for stage in method.stages
    }
    objective_artifact = {
        "artifact_id": "initialization:objective:1:1",
        "kind": "objective",
        "storage_class": "repository_ref",
        "stage": "initialization",
        "producer_attempt": 1,
        "producer_role": "controller",
        "path": objective,
        "sha256": digest_bytes((root / objective).read_bytes()),
        "input_artifacts": [],
        "status": "accepted",
        "invalidated_by_event": None,
        "accepted_at": manifest["created_at"],
    }
    stages["initialization"]["artifact_ids"] = [objective_artifact["artifact_id"]]
    checkpoint = {
        "schema_version": RUN_SCHEMA,
        "initiative_id": initiative_id,
        "manifest_digest": digest_json(manifest),
        "revision": 0,
        "event_hash": "0" * 64,
        "current_stage": method.stages[1],
        "stages": stages,
        "attempt_history": [],
        "artifacts": [objective_artifact],
        "gates": {"baseline": {}, "integration": {}, "acceptance": {}},
        "decisions": [],
        "delivery": {"adapter": None, "state": "not_started", "intent": None, "outcome": None, "attempts": 0},
        "usage": {"agent_calls": 0, "agent_call_overrides": 0, "parallel_peak": 0, "retries": {}, "retry_overrides": {}, "consecutive_rejections": 0},
        "blockers": [],
        "baseline": None,
        "review_snapshot": None,
        "acceptance_seal": None,
        "closed_at": None,
        "quarantined": False,
    }
    runs_root.mkdir(parents=True, exist_ok=True)
    temporary = runs_root / f".init-{initiative_id}-{os.getpid()}-{time.time_ns()}"
    temporary.mkdir()
    try:
        write_json_atomic(temporary / "manifest.json", manifest)
        _crash_point("initialization_after_manifest")
        write_json_atomic(temporary / "checkpoint.json", checkpoint)
        _crash_point("initialization_after_checkpoint")
        with (temporary / "events.jsonl").open("wb") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        _derive_views(temporary, manifest, checkpoint, method)
        _crash_point("initialization_before_publish")
        os.replace(temporary, run_dir)
        _fsync_directory(runs_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return run_dir


def _load_run(run_dir: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any], Method]:
    manifest = read_json(run_dir / "manifest.json")
    if manifest.get("schema_version") != RUN_SCHEMA:
        raise HarnessError("v1 and unknown Initiative records require a new v2 run")
    method_record = manifest.get("method", {})
    method_relative = str(method_record.get("path", ""))
    pinned_path = root / method_relative
    observed_digests = {name: digest_bytes((pinned_path / name).read_bytes()) for name in (*METHOD_TEXT_FILES, *METHOD_JSON_FILES) if (pinned_path / name).is_file()}
    if observed_digests != method_record.get("digests"):
        raise HarnessError("pinned development method changed or is unavailable")
    method = load_method(root, method_relative)
    if method_record.get("version") != method.version or method_record.get("digests") != method.digests:
        raise HarnessError("pinned development method changed or is unavailable")
    checkpoint = read_json(run_dir / "checkpoint.json")
    if checkpoint.get("schema_version") != RUN_SCHEMA:
        raise HarnessError("unsupported checkpoint schema")
    if checkpoint.get("manifest_digest") != digest_json(manifest):
        raise HarnessError("immutable manifest digest is invalid")
    reject_secrets(manifest)
    reject_secrets(checkpoint)
    return manifest, checkpoint, method


@contextmanager
def writer_lock(run_dir: Path, timeout_seconds: float = 2.0) -> Iterator[None]:
    path = run_dir / "writer.lock"
    handle = path.open("a+b")
    deadline = time.monotonic() + timeout_seconds
    locked = False
    try:
        while time.monotonic() < deadline and not locked:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0, os.SEEK_END)
                    if handle.tell() == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                time.sleep(0.02)
        if not locked:
            raise HarnessError("another Controller owns the Initiative writer lock")
        yield
    finally:
        if locked:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise HarnessError("event stream is missing")
    result: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError
                result.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise HarnessError("event stream is corrupt") from exc
    return result


def _validate_event_chain(events: list[dict[str, Any]]) -> None:
    previous = "0" * 64
    for index, event in enumerate(events, 1):
        if event.get("revision") != index or event.get("previous_hash") != previous:
            raise HarnessError("event revision or previous hash is invalid")
        body = {key: value for key, value in event.items() if key != "event_hash"}
        if event.get("event_hash") != digest_json(body):
            raise HarnessError("event hash is invalid")
        previous = event["event_hash"]


def recover_run(run_dir: Path) -> None:
    checkpoint = read_json(run_dir / "checkpoint.json")
    events = _read_events(run_dir / "events.jsonl")
    _validate_event_chain(events)
    prepared_path = run_dir / "checkpoint.prepared.json"
    if prepared_path.exists():
        prepared = read_json(prepared_path)
        expected = checkpoint["revision"] + 1
        event = events[-1] if events and events[-1].get("revision") == expected else None
        if event is None:
            prepared_path.unlink()
        elif prepared.get("revision") == expected and prepared.get("event_hash") == event.get("event_hash"):
            os.replace(prepared_path, run_dir / "checkpoint.json")
            _fsync_directory(run_dir)
            checkpoint = prepared
        else:
            raise HarnessError("prepared checkpoint cannot be reconciled")
    tail_revision = events[-1]["revision"] if events else 0
    tail_hash = events[-1]["event_hash"] if events else "0" * 64
    if checkpoint.get("revision") != tail_revision or checkpoint.get("event_hash") != tail_hash:
        raise HarnessError("checkpoint and event tail disagree")
    if events:
        state = {key: value for key, value in checkpoint.items() if key != "event_hash"}
        if events[-1].get("payload_digest") != digest_json(state):
            raise HarnessError("checkpoint payload does not match the committed event")


def _crash_point(name: str) -> None:
    if os.environ.get("KNOARBOR_HARNESS_CRASH_AT") == name:
        raise RuntimeError(f"simulated crash at {name}")


def mutate(
    run_dir: Path,
    root: Path,
    action: str,
    event_data: dict[str, Any],
    mutator: Callable[[dict[str, Any], dict[str, Any], Method], None],
) -> dict[str, Any]:
    with writer_lock(run_dir):
        recover_run(run_dir)
        manifest, checkpoint, method = _load_run(run_dir, root)
        if checkpoint.get("quarantined"):
            raise HarnessError("Initiative is quarantined")
        if checkpoint.get("closed_at"):
            raise HarnessError("closed Initiatives are immutable")
        next_checkpoint = deepcopy(checkpoint)
        mutator(next_checkpoint, manifest, method)
        reject_secrets(next_checkpoint)
        reject_private_paths(next_checkpoint)
        reject_secrets(event_data, "event")
        reject_private_paths(event_data, "event")
        revision = checkpoint["revision"] + 1
        next_checkpoint["revision"] = revision
        state = {key: value for key, value in next_checkpoint.items() if key != "event_hash"}
        event_body = {
            "revision": revision,
            "previous_hash": checkpoint["event_hash"],
            "timestamp": now(),
            "action": action,
            "data": event_data,
            "payload_digest": digest_json(state),
        }
        event = {**event_body, "event_hash": digest_json(event_body)}
        next_checkpoint["event_hash"] = event["event_hash"]
        prepared = run_dir / "checkpoint.prepared.json"
        write_json_atomic(prepared, next_checkpoint)
        _crash_point("after_prepare")
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _crash_point("after_event")
        os.replace(prepared, run_dir / "checkpoint.json")
        _fsync_directory(run_dir)
        _crash_point("after_replace")
        _derive_views(run_dir, manifest, next_checkpoint, method)
        return next_checkpoint


def _derive_views(run_dir: Path, manifest: dict[str, Any], checkpoint: dict[str, Any], method: Method) -> None:
    metrics = derive_metrics(run_dir, checkpoint)
    handoff = handoff_record(manifest, checkpoint, method, metrics)
    values = {
        "artifacts": {"schema_version": RUN_SCHEMA, "artifacts": checkpoint["artifacts"]},
        "baseline": {"schema_version": RUN_SCHEMA, "baseline": checkpoint.get("baseline")},
        "gates": {"schema_version": RUN_SCHEMA, "gates": checkpoint["gates"]},
        "decisions": {"schema_version": RUN_SCHEMA, "decisions": checkpoint["decisions"]},
        "delivery": {"schema_version": RUN_SCHEMA, "delivery": checkpoint["delivery"]},
        "metrics": {"schema_version": RUN_SCHEMA, **metrics},
        "handoff": handoff,
    }
    for name, value in values.items():
        write_json_atomic(run_dir / f"{name}.json", value)


def _consistent_run(run_dir: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any], Method]:
    with writer_lock(run_dir):
        recover_run(run_dir)
        manifest, checkpoint, method = _load_run(run_dir, root)
        _derive_views(run_dir, manifest, checkpoint, method)
        return manifest, checkpoint, method


def initiative_status(run_dir: Path, root: Path) -> dict[str, Any]:
    _, checkpoint, _ = _consistent_run(run_dir, root)
    return checkpoint


def validate_run(run_dir: Path, root: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest, checkpoint, method = _consistent_run(run_dir, root)
        if checkpoint.get("initiative_id") != manifest.get("initiative_id"):
            errors.append("manifest and checkpoint Initiative IDs differ")
        if tuple(checkpoint.get("stages", {})) != tuple(method.stages):
            errors.append("checkpoint stage vocabulary differs from pinned workflow")
        accepted_ids = {item["artifact_id"] for item in checkpoint.get("artifacts", []) if item.get("status") == "accepted"}
        for stage in checkpoint.get("stages", {}).values():
            if any(item not in accepted_ids for item in stage.get("artifact_ids", [])):
                errors.append("stage references a non-accepted artifact")
        if checkpoint.get("closed_at") and checkpoint["stages"]["closure"]["status"] != "passed":
            errors.append("closed_at requires passed closure")
        if checkpoint["stages"]["closure"]["status"] == "passed" and not checkpoint.get("acceptance_seal"):
            errors.append("closed Initiative lacks acceptance seal")
        for artifact in checkpoint.get("artifacts", []):
            if artifact.get("storage_class") == "repository_ref" and artifact.get("status") == "accepted":
                path = root / artifact["path"]
                if not path.is_file() or digest_bytes(path.read_bytes()) != artifact["sha256"]:
                    if not checkpoint.get("closed_at"):
                        errors.append(f"accepted artifact changed: {artifact['artifact_id']}")
    except HarnessError as exc:
        errors.append(str(exc))
    return errors


def _current(checkpoint: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    stage_id = checkpoint["current_stage"]
    return stage_id, checkpoint["stages"][stage_id]


def _next_stage(checkpoint: dict[str, Any], method: Method) -> str:
    for stage_id in method.stages:
        if checkpoint["stages"][stage_id]["status"] not in RESOLVED:
            return stage_id
    return "closure"


def _ensure_open(checkpoint: dict[str, Any]) -> None:
    if checkpoint.get("closed_at"):
        raise HarnessError("closed Initiatives are immutable")


def start_stage(run_dir: Path, root: Path, *, actor: str) -> None:
    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        stage_id, stage = _current(checkpoint)
        contract = method.stage(stage_id)
        expected = manifest["roles"][contract["owner"]]
        if actor != expected:
            raise HarnessError(f"stage {stage_id} requires {contract['owner']} execution identity")
        if stage["status"] not in {"pending", "failed"}:
            raise HarnessError("only a pending or failed current stage can start")
        verify_accepted_artifacts(checkpoint, root)
        stage.update({"status": "running", "attempt": stage["attempt"] + 1, "actor": actor, "entered_at": now(), "resolved_at": None, "reason": None})
        if contract["owner"] == "reviewer":
            checkpoint["review_snapshot"] = repository_fingerprints(root, run_dir.parent)

    mutate(run_dir, root, "stage_started", {"actor": actor}, change)


def skip_stage(run_dir: Path, root: Path, *, actor: str, skip_type: str, reason_code: str) -> None:
    bounded_text(actor, "actor", maximum=160)
    bounded_text(reason_code, "reason_code", maximum=120, token=True)
    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        stage_id, stage = _current(checkpoint)
        contract = method.stage(stage_id)
        if manifest["route"] in contract["required_by"]:
            raise HarnessError(f"route {manifest['route']} cannot skip {stage_id}")
        if skip_type not in contract.get("skip_types", []):
            raise HarnessError("skip type is not allowed for this stage")
        if actor != manifest["roles"][contract["owner"]]:
            raise HarnessError("wrong execution identity for skip")
        stage.update({"status": "skipped", "actor": actor, "attempt": max(1, stage["attempt"]), "entered_at": stage["entered_at"] or now(), "resolved_at": now(), "skip_type": skip_type, "reason": reason_code})
        checkpoint["usage"]["consecutive_rejections"] = 0
        checkpoint["current_stage"] = _next_stage(checkpoint, method)

    mutate(run_dir, root, "stage_skipped", {"actor": actor, "skip_type": skip_type, "reason_code": reason_code}, change)


def _accepted_artifacts(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in checkpoint["artifacts"] if item.get("status") == "accepted"]


def verify_accepted_artifacts(checkpoint: dict[str, Any], root: Path) -> None:
    for artifact in _accepted_artifacts(checkpoint):
        if artifact["storage_class"] != "repository_ref":
            continue
        path = root / artifact["path"]
        if not path.is_file() or digest_bytes(path.read_bytes()) != artifact["sha256"]:
            raise HarnessError(f"accepted upstream artifact changed: {artifact['artifact_id']}")


def submit_artifact(
    run_dir: Path,
    root: Path,
    *,
    actor: str,
    kind: str,
    path: str | None = None,
    control: dict[str, Any] | None = None,
) -> str:
    result: dict[str, str] = {}

    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        stage_id, stage = _current(checkpoint)
        definition = method.artifact(kind)
        if definition["stage"] != stage_id:
            raise HarnessError(f"artifact {kind} does not belong to {stage_id}")
        producer = definition["producer"]
        if actor != manifest["roles"][producer]:
            raise HarnessError(f"artifact {kind} requires {producer} execution identity")
        if stage["status"] != "running":
            raise HarnessError("stage must be running before artifact submission")
        existing = [item for item in checkpoint["artifacts"] if item["kind"] == kind and item["producer_attempt"] == stage["attempt"]]
        if existing and not definition.get("multiple"):
            raise HarnessError(f"artifact {kind} already exists for this attempt")
        artifact_id = f"{stage_id}:{kind}:{stage['attempt']}:{len(existing) + 1}"
        artifact: dict[str, Any] = {
            "artifact_id": artifact_id,
            "kind": kind,
            "storage_class": definition["storage_class"],
            "stage": stage_id,
            "producer_attempt": stage["attempt"],
            "producer_role": producer,
            "input_artifacts": [item["artifact_id"] for item in _accepted_artifacts(checkpoint)],
            "status": "accepted",
            "invalidated_by_event": None,
            "accepted_at": now(),
        }
        if definition["storage_class"] == "repository_ref":
            if path is None or control is not None:
                raise HarnessError("repository artifact requires only a path")
            normalized = normalized_paths([path], root)[0]
            if not path_allowed(normalized, manifest["allowed_paths"]):
                raise HarnessError("artifact path is outside frozen Initiative scope")
            target = root / normalized
            if not target.is_file():
                raise HarnessError("artifact path must be an existing file")
            if definition.get("path_suffix") and not normalized.endswith(definition["path_suffix"]):
                raise HarnessError(f"artifact {kind} must reference {definition['path_suffix']}")
            artifact.update({"path": normalized, "sha256": digest_bytes(target.read_bytes())})
        else:
            if path is not None or not isinstance(control, dict):
                raise HarnessError("control artifact requires a structured record")
            allowed_fields = {"outcome", "finding_ids", "rollback_target", "summary_code", "gate_ids"}
            if set(control) - allowed_fields:
                raise HarnessError("control record contains an unsupported field")
            if control.get("outcome") not in {"approved", "rejected", "passed", "failed", "delivered"}:
                raise HarnessError("control record has an invalid outcome")
            if any(not isinstance(value, str) or len(value) > 160 for value in control.get("finding_ids", [])):
                raise HarnessError("finding IDs must be short strings")
            for index, value in enumerate(control.get("finding_ids", [])):
                bounded_text(value, f"control_record.finding_ids[{index}]", maximum=160, token=True)
            if "summary_code" in control:
                bounded_text(control["summary_code"], "control_record.summary_code", maximum=120, token=True)
            if "rollback_target" in control:
                rollback_target = bounded_text(control["rollback_target"], "control_record.rollback_target", maximum=80, token=True)
                if rollback_target not in method.stages:
                    raise HarnessError("control record rollback target is unknown")
            gate_ids = control.get("gate_ids", [])
            if not isinstance(gate_ids, list):
                raise HarnessError("control record gate_ids must be a list")
            for index, value in enumerate(gate_ids):
                bounded_text(value, f"control_record.gate_ids[{index}]", maximum=120, token=True)
                method.gate(value)
            reject_secrets(control, "control_record")
            artifact["control"] = control
            artifact["sha256"] = digest_json(control)
        checkpoint["artifacts"].append(artifact)
        stage["artifact_ids"].append(artifact_id)
        result["artifact_id"] = artifact_id

    mutate(run_dir, root, "artifact_submitted", {"actor": actor, "kind": kind}, change)
    return result["artifact_id"]


def _required_outputs(method: Method, stage_id: str, route: str) -> list[str]:
    return list(method.artifacts.get("required_outputs", {}).get(stage_id, []))


def complete_stage(run_dir: Path, root: Path, *, actor: str) -> None:
    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        stage_id, stage = _current(checkpoint)
        contract = method.stage(stage_id)
        if contract.get("human") or stage_id in {"workspace_baseline", "acceptance", "closure"}:
            raise HarnessError(f"stage {stage_id} requires its dedicated command")
        if actor != manifest["roles"][contract["owner"]] or stage["status"] != "running":
            raise HarnessError("wrong execution identity or stage is not running")
        accepted_kinds = {item["kind"] for item in _accepted_artifacts(checkpoint) if item["stage"] == stage_id and item["producer_attempt"] == stage["attempt"]}
        missing = sorted(set(_required_outputs(method, stage_id, manifest["route"])) - accepted_kinds)
        if missing:
            raise HarnessError("stage lacks required artifacts: " + ", ".join(missing))
        if stage_id == "integration":
            delta = gate_delta_from_checkpoint(checkpoint, "integration")
            if delta["blockers"]:
                raise HarnessError("integration gate delta blocks completion: " + "; ".join(delta["blockers"]))
        for item in _accepted_artifacts(checkpoint):
            if item["stage"] != stage_id or item["producer_attempt"] != stage["attempt"] or item["storage_class"] != "control_record":
                continue
            if item["control"]["outcome"] not in method.artifact(item["kind"])["success_outcomes"]:
                raise HarnessError(f"control artifact does not record success: {item['kind']}")
        verify_accepted_artifacts(checkpoint, root)
        if contract["owner"] == "reviewer":
            current = repository_fingerprints(root, run_dir.parent)
            if current != checkpoint.get("review_snapshot"):
                raise HarnessError("Reviewer mutated the repository")
            checkpoint["review_snapshot"] = None
        stage.update({"status": "passed", "resolved_at": now()})
        if contract["owner"] == "reviewer":
            checkpoint["usage"]["consecutive_rejections"] = 0
        checkpoint["current_stage"] = _next_stage(checkpoint, method)

    mutate(run_dir, root, "stage_completed", {"actor": actor}, change)


def approve_stage(run_dir: Path, root: Path, *, actor: str) -> None:
    bounded_text(actor, "actor", maximum=160)
    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        stage_id, stage = _current(checkpoint)
        contract = method.stage(stage_id)
        if not contract.get("human"):
            raise HarnessError("current stage is not a human decision")
        if stage_id == "acceptance":
            _assert_acceptance_ready(checkpoint, manifest, method, root, run_dir.parent)
        decision_id = f"decision:{stage_id}:{stage['attempt'] + 1}:approve"
        decision = {"decision_id": decision_id, "stage": stage_id, "decision": "approve", "actor": actor, "timestamp": now(), "rollback_target": None}
        checkpoint["decisions"].append(decision)
        stage.update({"status": "passed", "attempt": stage["attempt"] + 1, "actor": actor, "entered_at": stage["entered_at"] or now(), "resolved_at": now(), "reason": None})
        if stage_id == "acceptance":
            _add_control_artifact(checkpoint, manifest, method, "acceptance_verdict", {"outcome": "approved", "finding_ids": [], "gate_ids": sorted(checkpoint["gates"]["acceptance"])})
            seal = _workspace_snapshot(root, run_dir.parent, manifest, method)
            seal["artifact_digests"] = sorted((item["artifact_id"], item["sha256"]) for item in _accepted_artifacts(checkpoint))
            seal["gates_digest"] = digest_json(checkpoint["gates"])
            seal["evidence_root_hash"] = digest_json({key: value for key, value in seal.items() if key != "evidence_root_hash"})
            checkpoint["acceptance_seal"] = seal
        if contract["owner"] == "reviewer":
            checkpoint["usage"]["consecutive_rejections"] = 0
        checkpoint["current_stage"] = _next_stage(checkpoint, method)

    mutate(run_dir, root, "human_approved", {"actor": actor}, change)


def reject_stage(run_dir: Path, root: Path, *, actor: str, rollback_target: str, finding_ids: list[str]) -> None:
    bounded_text(actor, "actor", maximum=160)
    if not finding_ids:
        raise HarnessError("rejection requires at least one finding ID")
    for index, finding_id in enumerate(finding_ids):
        bounded_text(finding_id, f"finding_ids[{index}]", maximum=160, token=True)
    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        stage_id, stage = _current(checkpoint)
        contract = method.stage(stage_id)
        if not contract.get("human") and actor != manifest["roles"][contract["owner"]]:
            raise HarnessError("wrong execution identity for rejection")
        if not contract.get("human") and stage["status"] != "running":
            raise HarnessError("Reviewer rejection requires a running review stage")
        if not actor:
            raise HarnessError("rejection requires an actor")
        if rollback_target not in contract.get("rollback", []):
            raise HarnessError("rollback target is not permitted for the current stage")
        decision_id = f"decision:{stage_id}:{stage['attempt'] + 1}:reject"
        checkpoint["decisions"].append({"decision_id": decision_id, "stage": stage_id, "decision": "reject", "actor": actor, "timestamp": now(), "rollback_target": rollback_target, "finding_ids": finding_ids})
        target_index = method.stages.index(rollback_target)
        for artifact in checkpoint["artifacts"]:
            if artifact["status"] == "accepted" and method.stages.index(artifact["stage"]) >= target_index:
                artifact["status"] = "invalidated"
                artifact["invalidated_by_event"] = checkpoint["revision"] + 1
        for index, candidate in enumerate(method.stages):
            if index >= target_index:
                prior = checkpoint["stages"][candidate]
                if prior["attempt"]:
                    checkpoint["attempt_history"].append({"stage": candidate, **deepcopy(prior)})
                prior_attempt = prior["attempt"]
                checkpoint["stages"][candidate] = {"status": "pending", "attempt": prior_attempt, "actor": None, "entered_at": None, "resolved_at": None, "reason": None, "skip_type": None, "artifact_ids": [], "rollback_source": stage_id}
        usage = checkpoint["usage"]
        usage["consecutive_rejections"] += 1
        checkpoint["current_stage"] = rollback_target
        if usage["consecutive_rejections"] >= method.workflow["rejection_limit"]:
            checkpoint["stages"][rollback_target]["status"] = "awaiting_human"
            checkpoint["blockers"].append("rejection_circuit_breaker")
        if stage_id == "acceptance":
            checkpoint["gates"]["acceptance"] = {}
            checkpoint["acceptance_seal"] = None
        if target_index <= method.stages.index("integration"):
            checkpoint["gates"]["integration"] = {}

    mutate(run_dir, root, "stage_rejected", {"actor": actor, "rollback_target": rollback_target, "finding_ids": finding_ids}, change)


def recover_human(run_dir: Path, root: Path, *, actor: str) -> None:
    bounded_text(actor, "actor", maximum=160)
    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        stage_id, stage = _current(checkpoint)
        if stage["status"] != "awaiting_human":
            raise HarnessError("current stage is not awaiting human recovery")
        if "agent_call_budget_exceeded" in checkpoint["blockers"]:
            checkpoint["usage"]["agent_call_overrides"] += 1
        if "retry_budget_exceeded" in checkpoint["blockers"]:
            overrides = checkpoint["usage"]["retry_overrides"]
            overrides[stage_id] = overrides.get(stage_id, 0) + 1
        stage["status"] = "pending"
        stage["reason"] = f"recovered_by:{actor}"
        checkpoint["usage"]["consecutive_rejections"] = 0
        checkpoint["blockers"] = [item for item in checkpoint["blockers"] if item not in {"rejection_circuit_breaker", "agent_call_budget_exceeded", "retry_budget_exceeded"}]

    mutate(run_dir, root, "human_recovered", {"actor": actor}, change)


def record_agent_call(run_dir: Path, root: Path, *, role: str, parallel_children: int) -> None:
    exceeded: list[bool] = []

    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        if role not in manifest["roles"] or parallel_children != 1:
            raise HarnessError("unknown role or v2 parallel-child violation")
        usage = checkpoint["usage"]
        if usage["agent_calls"] + 1 > manifest["budgets"]["max_agent_calls"] + usage["agent_call_overrides"]:
            checkpoint["stages"][checkpoint["current_stage"]]["status"] = "awaiting_human"
            checkpoint["blockers"].append("agent_call_budget_exceeded")
            exceeded.append(True)
        else:
            usage["agent_calls"] += 1
            usage["parallel_peak"] = max(usage["parallel_peak"], parallel_children)

    mutate(run_dir, root, "agent_call_recorded", {"role": role, "parallel_children": parallel_children}, change)
    if exceeded:
        raise HarnessError("Agent call budget exceeded; Initiative is awaiting human recovery")


def record_retry(run_dir: Path, root: Path) -> None:
    exceeded: list[bool] = []

    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        stage_id, stage = _current(checkpoint)
        retries = checkpoint["usage"]["retries"]
        retries[stage_id] = retries.get(stage_id, 0) + 1
        allowance = manifest["budgets"]["max_retries_per_stage"] + checkpoint["usage"]["retry_overrides"].get(stage_id, 0)
        if retries[stage_id] > allowance:
            stage["status"] = "awaiting_human"
            checkpoint["blockers"].append("retry_budget_exceeded")
            exceeded.append(True)

    mutate(run_dir, root, "retry_recorded", {}, change)
    if exceeded:
        raise HarnessError("retry budget exceeded; Initiative is awaiting human recovery")


def role_packet(run_dir: Path, root: Path) -> dict[str, Any]:
    manifest, checkpoint, method = _consistent_run(run_dir, root)
    stage_id, stage = _current(checkpoint)
    contract = method.stage(stage_id)
    role_id = contract["owner"]
    role = method.role(role_id)
    readable = []
    for artifact in _accepted_artifacts(checkpoint):
        if "*" in role["read_kinds"] or artifact["kind"] in role["read_kinds"]:
            readable.append({key: artifact[key] for key in ("artifact_id", "kind", "storage_class", "path", "sha256") if key in artifact})
    return {
        "schema_version": RUN_SCHEMA,
        "initiative_id": manifest["initiative_id"],
        "method": manifest["method"],
        "stage": stage_id,
        "attempt": stage["attempt"] + (0 if stage["status"] == "running" else 1),
        "role": role_id,
        "execution_id": manifest["roles"][role_id],
        "objective_ref": manifest["objective_ref"],
        "non_goals": manifest["non_goals"],
        "readable_artifacts": readable,
        "required_outputs": _required_outputs(method, stage_id, manifest["route"]),
        "allowed_write_paths": [] if role["repository_write"] == "none" else manifest["allowed_paths"],
        "forbidden": role["forbidden"],
        "rollback_targets": contract["rollback"],
        "remaining_agent_calls": manifest["budgets"]["max_agent_calls"] - checkpoint["usage"]["agent_calls"],
        "remaining_stage_retries": manifest["budgets"]["max_retries_per_stage"] + checkpoint["usage"].get("retry_overrides", {}).get(stage_id, 0) - checkpoint["usage"]["retries"].get(stage_id, 0),
    }


def _workspace_snapshot(root: Path, runs_root: Path, manifest: dict[str, Any], method: Method) -> dict[str, Any]:
    return {
        "branch": _git(root, "branch", "--show-current"),
        "head": _git(root, "rev-parse", "HEAD"),
        "method_digests": method.digests,
        "allowed_paths": manifest["allowed_paths"],
        "file_fingerprints": repository_fingerprints(root, runs_root),
        "captured_at": now(),
    }


def capture_workspace_baseline(run_dir: Path, root: Path) -> None:
    def begin(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        _ensure_open(checkpoint)
        stage_id, stage = _current(checkpoint)
        if stage_id != "workspace_baseline" or stage["status"] not in {"pending", "running"}:
            raise HarnessError("workspace baseline is not the current stage")
        if checkpoint.get("baseline"):
            if stage["status"] != "running":
                raise HarnessError("workspace baseline is immutable once captured")
            return
        stage.update({"status": "running", "attempt": max(1, stage["attempt"] + (stage["status"] == "pending")), "actor": manifest["roles"]["controller"], "entered_at": stage["entered_at"] or now()})
        checkpoint["baseline"] = _workspace_snapshot(root, run_dir.parent, manifest, method)

    mutate(run_dir, root, "workspace_baseline_captured", {}, begin)
    run_gates(run_dir, root, phase="baseline")

    def finish(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        stage = checkpoint["stages"]["workspace_baseline"]
        if checkpoint["current_stage"] != "workspace_baseline" or not checkpoint["gates"]["baseline"]:
            raise HarnessError("baseline gates were not recorded")
        stage.update({"status": "passed", "resolved_at": now()})
        checkpoint["current_stage"] = _next_stage(checkpoint, method)

    mutate(run_dir, root, "workspace_baseline_completed", {}, finish)


def verify_scope(run_dir: Path, root: Path) -> dict[str, Any]:
    manifest, checkpoint, _ = _consistent_run(run_dir, root)
    baseline = checkpoint.get("baseline")
    if not baseline:
        raise HarnessError("workspace baseline is missing")
    current = repository_fingerprints(root, run_dir.parent)
    previous = baseline["file_fingerprints"]
    changed = sorted(path for path in set(previous) | set(current) if previous.get(path) != current.get(path))
    overflow = [path for path in changed if not path_allowed(path, manifest["allowed_paths"])]
    return {"changed_after_baseline": changed, "scope_overflow": overflow}


def _expanded_allowed_paths(root: Path, allowed: Sequence[str]) -> list[str]:
    tracked = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    result: set[str] = set()
    for rule in allowed:
        if rule.endswith("/"):
            result.update(path for path in tracked if path and path.startswith(rule))
        else:
            result.add(rule)
    return sorted(result)


def _gate_applies(gate: dict[str, Any], manifest: dict[str, Any]) -> bool:
    condition = gate.get("condition")
    allowed = manifest["allowed_paths"]
    if condition in {"always", "explicit", "release"}:
        return True
    if condition == "renderer_scope":
        return any(path.startswith("renderer/") for path in allowed)
    if condition == "desktop_scope":
        return any(path.startswith("desktop/") for path in allowed)
    return False


def _sanitized_gate_output(output: bytes, root: Path) -> tuple[str, str]:
    text = output.decode("utf-8", errors="replace")
    redacted = text
    for root_value in sorted({str(root), str(root.resolve())}, key=len, reverse=True):
        redacted = redacted.replace(root_value, "<repo>")
    redacted = redacted.replace(str(Path.home()), "<home>")
    for value in os.environ.values():
        if len(value) >= 4:
            redacted = redacted.replace(value, "<env>")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    redacted = CANARY_PATH_PATTERN.sub("<private-path>", redacted)
    redacted = GATE_PRIVATE_PATH_PATTERN.sub("<private-path>", redacted)
    return text, redacted


def _stable_diagnostic_line(line: str) -> str:
    stable = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip()
    for pattern, replacement in VOLATILE_OUTPUT_PATTERNS:
        stable = pattern.sub(replacement, stable)
    stable = re.sub(r"\s+", " ", stable)
    return stable


def _diagnostic_projection(redacted: str, returncode: int) -> list[str]:
    if returncode == 0:
        return ["exit:0"]
    lines = [_stable_diagnostic_line(line) for line in redacted.splitlines() if line.strip()]
    diagnostics = []
    for line in lines:
        file_diagnostic = DIAGNOSTIC_FILE_PATTERN.search(line) and (
            "<repo>/" in line
            or line.startswith("File ")
            or re.search(r"\b(?:error|fail(?:ed|ure)?|warning)\b", line, re.IGNORECASE)
        )
        if any(pattern.search(line) for pattern in DIAGNOSTIC_LINE_PATTERNS) or file_diagnostic:
            diagnostics.append(line)
    if diagnostics:
        return [f"exit:{returncode}", *diagnostics]
    non_logs = [
        line for line in lines
        if not re.match(r"^(?:\[?\d{1,3}%\]?|[.FsE]+$|Ran \d+ tests? in\b|[-=]{3,}$)", line)
        and not re.match(r"^(?:DEBUG|INFO|TRACE)\b", line, re.IGNORECASE)
    ]
    return [
        f"exit:{returncode}",
        f"opaque-set:{digest_json(non_logs)}",
        *non_logs[-20:],
    ]


def _redacted_summary(output: bytes, root: Path, returncode: int, gate_id: str, elapsed_ms: int) -> dict[str, Any]:
    text, redacted = _sanitized_gate_output(output, root)
    locations = {
        value
        for value in re.findall(r"<repo>/([A-Za-z0-9_./-]+\.(?:py|ts|tsx|md|json))", redacted)
        if ".." not in Path(value).parts and (root / value).is_file()
    }
    for match in DIAGNOSTIC_FILE_PATTERN.finditer(redacted):
        value = match.group("path")
        if not value.startswith(("/", "<")) and ".." not in Path(value).parts and (root / value).is_file():
            locations.add(value)
    projection = _diagnostic_projection(redacted, returncode)
    fingerprint_projection = {
        "diagnostics": projection,
        "locations": sorted(locations),
    }
    return {
        "gate_id": gate_id,
        "exit_code": returncode,
        "duration_ms": elapsed_ms,
        "output_fingerprint": digest_json(fingerprint_projection),
        "output_lines": len(text.splitlines()),
        "diagnostic_locations": sorted(locations)[:20],
    }


def _secret_scan(root: Path, paths: Sequence[str]) -> tuple[int, bytes]:
    findings: list[str] = []
    for relative in paths:
        path = root / relative
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            findings.append(relative)
    message = f"secret categories found in {len(findings)} files".encode()
    return (1 if findings else 0), message


def run_gates(run_dir: Path, root: Path, *, phase: str) -> dict[str, Any]:
    if phase not in {"baseline", "integration", "acceptance"}:
        raise HarnessError("gate phase must be baseline, integration, or acceptance")
    manifest, checkpoint, _ = _consistent_run(run_dir, root)
    if not checkpoint.get("baseline"):
        raise HarnessError("workspace baseline must be captured before gates")
    expected_stage = {"baseline": "workspace_baseline", "integration": "integration", "acceptance": "acceptance"}[phase]
    if checkpoint["current_stage"] != expected_stage or checkpoint["stages"][expected_stage]["status"] != "running":
        raise HarnessError(f"{phase} gates require a running {expected_stage} stage")
    results: dict[str, Any] = {}
    expanded = _expanded_allowed_paths(root, manifest["allowed_paths"])
    for gate in manifest["effective_gates"]:
        if phase not in gate["phases"] or not _gate_applies(gate, manifest):
            continue
        existing = checkpoint["gates"][phase].get(gate["id"])
        if existing:
            results[gate["id"]] = existing
            continue
        started = time.monotonic()
        if gate["executor"] == "internal_secret_scan":
            exit_code, output = _secret_scan(root, expanded)
        elif gate["executor"] == "command":
            command: list[str] = []
            for argument in gate["command"]:
                if argument == "{allowed_paths}":
                    command.extend(expanded)
                else:
                    command.append(argument)
            try:
                process = subprocess.run(command, cwd=root, capture_output=True, timeout=gate["timeout_seconds"], check=False)
                exit_code = process.returncode
                output = process.stdout + b"\0" + process.stderr
            except subprocess.TimeoutExpired as exc:
                exit_code = 124
                output = (exc.stdout or b"") + b"\0" + (exc.stderr or b"")
            except OSError:
                exit_code = 127
                output = b"process launch failed"
        else:
            exit_code, output = 2, b"external acceptance evidence not recorded"
        elapsed_ms = round((time.monotonic() - started) * 1000)
        summary = _redacted_summary(output, root, exit_code, gate["id"], elapsed_ms)
        result = {**summary, "severity": gate["severity"], "executor": gate["executor"], "baseline_required": "baseline" in gate["phases"], "command_digest": digest_json(gate.get("command", [gate["executor"]])), "recorded_at": now(), "scar": None}

        def record(cp: dict[str, Any], _manifest: dict[str, Any], _method: Method, *, item: dict[str, Any] = result, gate_id: str = gate["id"]) -> None:
            cp["gates"][phase][gate_id] = item

        mutate(run_dir, root, "gate_recorded", {"phase": phase, "gate_id": gate["id"], "exit_code": exit_code}, record)
        print(f"gate {gate['id']}: exit={exit_code} duration_ms={elapsed_ms} lines={summary['output_lines']}")
        results[gate["id"]] = result
    return results


def record_external_gate(run_dir: Path, root: Path, *, gate_id: str, outcome: str, evidence_id: str, evidence_digest: str) -> None:
    if outcome not in {"passed", "failed"}:
        raise HarnessError("external gate outcome must be passed or failed")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", evidence_id):
        raise HarnessError("external gate evidence ID is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", evidence_digest):
        raise HarnessError("external gate evidence digest must be SHA-256 hex")

    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        if checkpoint["current_stage"] != "acceptance":
            raise HarnessError("external acceptance evidence requires the acceptance stage")
        selected = next((item for item in manifest["effective_gates"] if item["id"] == gate_id), None)
        if selected is None or selected["executor"] != "external_acceptance" or "acceptance" not in selected["phases"]:
            raise HarnessError("gate is not a selected external acceptance gate")
        if gate_id in checkpoint["gates"]["acceptance"]:
            raise HarnessError("external gate result is immutable once recorded")
        record = {
            "gate_id": gate_id,
            "exit_code": 0 if outcome == "passed" else 1,
            "duration_ms": 0,
            "output_fingerprint": evidence_digest,
            "output_lines": 0,
            "diagnostic_locations": [],
            "severity": selected["severity"],
            "executor": "external_acceptance",
            "baseline_required": "baseline" in selected["phases"],
            "command_digest": digest_json([selected["executor"]]),
            "recorded_at": now(),
            "evidence_id": evidence_id,
            "scar": None,
        }
        checkpoint["gates"]["acceptance"][gate_id] = record

    mutate(run_dir, root, "external_gate_recorded", {"gate_id": gate_id, "outcome": outcome, "evidence_id": evidence_id}, change)


def record_scar(run_dir: Path, root: Path, *, gate_id: str, owner: str, acknowledgement: str, expiry_or_removal: str) -> None:
    bounded_text(owner, "scar.owner", maximum=160)
    bounded_text(acknowledgement, "scar.acknowledgement")
    bounded_text(expiry_or_removal, "scar.expiry_or_removal")
    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        phase = checkpoint["current_stage"]
        if phase not in {"integration", "acceptance"}:
            raise HarnessError("soft scars may only be recorded during integration or acceptance")
        record = checkpoint["gates"][phase].get(gate_id)
        if not record or record["severity"] != "soft" or record["exit_code"] == 0:
            raise HarnessError("scar requires a failing soft acceptance gate")
        if record.get("scar"):
            raise HarnessError("soft scar is immutable once recorded")
        scar = {"owner": owner, "acknowledgement": acknowledgement, "expiry_or_removal": expiry_or_removal}
        reject_secrets(scar)
        if not all(isinstance(value, str) and value.strip() for value in scar.values()):
            raise HarnessError("scar fields must be non-empty")
        record["scar"] = scar

    mutate(run_dir, root, "soft_scar_recorded", {"gate_id": gate_id, "owner": owner}, change)


def gate_delta_from_checkpoint(checkpoint: dict[str, Any], phase: str = "acceptance") -> dict[str, Any]:
    baseline = checkpoint["gates"]["baseline"]
    acceptance = checkpoint["gates"][phase]
    blockers: list[str] = []
    preexisting: list[str] = []
    scars: list[str] = []
    if not baseline:
        blockers.append("no baseline gates")
    if not acceptance:
        blockers.append(f"no {phase} gates")
    for gate_id in sorted(set(baseline) | set(acceptance)):
        before = baseline.get(gate_id)
        after = acceptance.get(gate_id)
        if after is None:
            blockers.append(f"missing {phase} gate: {gate_id}")
            continue
        if before is None and after.get("baseline_required", True):
            blockers.append(f"unbaselined acceptance gate: {gate_id}")
        elif before is not None and before["severity"] != after["severity"]:
            blockers.append(f"gate severity drift: {gate_id}")
        if after["exit_code"] == 0:
            continue
        identical = before is not None and before["exit_code"] != 0 and before["output_fingerprint"] == after["output_fingerprint"]
        if identical:
            preexisting.append(gate_id)
            continue
        if after["severity"] == "hard":
            blockers.append(f"new hard failure: {gate_id}")
        elif not after.get("scar") or not all(after["scar"].values()):
            blockers.append(f"incomplete soft scar: {gate_id}")
        else:
            scars.append(gate_id)
    return {"blockers": blockers, "pre_existing_failures": preexisting, "accepted_soft_scars": scars}


def gate_delta(run_dir: Path, root: Path) -> dict[str, Any]:
    _, checkpoint, _ = _consistent_run(run_dir, root)
    return gate_delta_from_checkpoint(checkpoint)


def _assert_acceptance_ready(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method, root: Path, runs_root: Path) -> None:
    scope = verify_scope_from_checkpoint(checkpoint, manifest, root, runs_root)
    delta = gate_delta_from_checkpoint(checkpoint)
    if scope["scope_overflow"]:
        raise HarnessError("scope overflow blocks acceptance")
    if delta["blockers"]:
        raise HarnessError("gate delta blocks acceptance: " + "; ".join(delta["blockers"]))
    verify_accepted_artifacts(checkpoint, root)


def verify_scope_from_checkpoint(checkpoint: dict[str, Any], manifest: dict[str, Any], root: Path, runs_root: Path) -> dict[str, Any]:
    baseline = checkpoint.get("baseline")
    if not baseline:
        raise HarnessError("workspace baseline is missing")
    current = repository_fingerprints(root, runs_root)
    previous = baseline["file_fingerprints"]
    changed = sorted(path for path in set(previous) | set(current) if previous.get(path) != current.get(path))
    return {"changed_after_baseline": changed, "scope_overflow": [path for path in changed if not path_allowed(path, manifest["allowed_paths"])]}


def run_acceptance(run_dir: Path, root: Path) -> None:
    manifest, checkpoint, method = _consistent_run(run_dir, root)
    if checkpoint["current_stage"] != "acceptance":
        raise HarnessError("acceptance is not the current stage")

    def begin(cp: dict[str, Any], active_manifest: dict[str, Any], _method: Method) -> None:
        stage = cp["stages"]["acceptance"]
        if stage["status"] == "pending":
            stage.update({"status": "running", "attempt": stage["attempt"] + 1, "actor": active_manifest["roles"]["controller"], "entered_at": now()})
        elif stage["status"] != "running":
            raise HarnessError("acceptance stage cannot run gates from its current state")

    mutate(run_dir, root, "acceptance_started", {}, begin)
    run_gates(run_dir, root, phase="acceptance")
    _, checkpoint, _ = _load_run(run_dir, root)
    _assert_acceptance_ready(checkpoint, manifest, method, root, run_dir.parent)


def _add_control_artifact(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method, kind: str, control: dict[str, Any]) -> str:
    definition = method.artifact(kind)
    stage_id = definition["stage"]
    stage = checkpoint["stages"][stage_id]
    existing = [item for item in checkpoint["artifacts"] if item["kind"] == kind and item["producer_attempt"] == stage["attempt"]]
    artifact_id = f"{stage_id}:{kind}:{stage['attempt']}:{len(existing) + 1}"
    item = {"artifact_id": artifact_id, "kind": kind, "storage_class": "control_record", "stage": stage_id, "producer_attempt": stage["attempt"], "producer_role": definition["producer"], "input_artifacts": [artifact["artifact_id"] for artifact in _accepted_artifacts(checkpoint)], "status": "accepted", "invalidated_by_event": None, "accepted_at": now(), "control": control, "sha256": digest_json(control)}
    checkpoint["artifacts"].append(item)
    stage["artifact_ids"].append(artifact_id)
    return artifact_id


def deliver_local(run_dir: Path, root: Path) -> None:
    def change(checkpoint: dict[str, Any], manifest: dict[str, Any], method: Method) -> None:
        if checkpoint["current_stage"] != "closure" or checkpoint["stages"]["acceptance"]["status"] != "passed":
            raise HarnessError("local delivery requires passed acceptance and current closure")
        if checkpoint["delivery"]["state"] == "delivered":
            raise HarnessError("Initiative is already delivered")
        stage = checkpoint["stages"]["closure"]
        stage.update({"status": "running", "attempt": max(1, stage["attempt"] + (stage["status"] == "pending")), "actor": manifest["roles"]["controller"], "entered_at": stage["entered_at"] or now()})
        checkpoint["delivery"] = {"adapter": "local", "state": "delivered", "intent": {"idempotency_key": digest_json({"initiative": manifest["initiative_id"], "seal": checkpoint["acceptance_seal"]["evidence_root_hash"]})}, "outcome": {"kind": "portable_local_bundle", "timestamp": now()}, "attempts": checkpoint["delivery"]["attempts"] + 1}
        _add_control_artifact(checkpoint, manifest, method, "delivery_evidence", {"outcome": "delivered", "finding_ids": [], "summary_code": "local_bundle"})
        _add_control_artifact(checkpoint, manifest, method, "handoff", {"outcome": "delivered", "finding_ids": [], "summary_code": "handoff_ready"})

    mutate(run_dir, root, "local_delivery_completed", {}, change)


def _command_result(runner: Callable[..., subprocess.CompletedProcess[Any]], command: list[str], root: Path) -> subprocess.CompletedProcess[Any]:
    try:
        return runner(command, cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return subprocess.CompletedProcess(command, 127, "", "")


def deliver_github(
    run_dir: Path,
    root: Path,
    *,
    base_ref: str,
    head_ref: str,
    dry_run: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> dict[str, Any]:
    bounded_text(base_ref, "base_ref", maximum=160)
    bounded_text(head_ref, "head_ref", maximum=160)
    manifest, checkpoint, method = _consistent_run(run_dir, root)
    if checkpoint["current_stage"] != "closure" or checkpoint["stages"]["acceptance"]["status"] != "passed":
        raise HarnessError("GitHub delivery requires current closure after acceptance")
    if "github_pr" not in manifest["authorized_side_effects"]:
        raise HarnessError("github_pr side effect was not authorized")
    if _git(root, "status", "--porcelain"):
        raise HarnessError("GitHub delivery requires a clean worktree")
    oid = _git(root, "rev-parse", "HEAD")
    if checkpoint["acceptance_seal"]["head"] != oid:
        raise HarnessError("HEAD differs from the accepted OID")
    if checkpoint["delivery"]["state"] == "delivered":
        raise HarnessError("Initiative is already delivered")
    remote = _git(root, "config", "--get", "remote.origin.url")
    marker = f"[knoarbor-initiative:{manifest['initiative_id']}:{oid}]"
    preflight = {"remote_digest": digest_bytes(remote.encode()), "base_ref": base_ref, "head_ref": head_ref, "accepted_head_oid": oid, "initiative_marker": marker}

    def intent(cp: dict[str, Any], _manifest: dict[str, Any], _method: Method) -> None:
        stage = cp["stages"]["closure"]
        stage.update({"status": "running", "attempt": max(1, stage["attempt"] + (stage["status"] == "pending")), "actor": manifest["roles"]["controller"], "entered_at": stage["entered_at"] or now()})
        cp["delivery"] = {"adapter": "github", "state": "intent_recorded", "intent": {"preflight": preflight, "digest": digest_json(preflight)}, "outcome": None, "attempts": cp["delivery"]["attempts"] + 1}

    mutate(run_dir, root, "github_delivery_intent", {"identity_digest": digest_json(preflight)}, intent)
    if dry_run:
        return {"state": "planned", "identity": preflight}
    remote_line = _git(root, "ls-remote", "origin", f"refs/heads/{head_ref}", check=False)
    if not remote_line or remote_line.split()[0] != oid:
        _record_delivery_failure(run_dir, root, "remote_head_mismatch")
        raise HarnessError("remote head does not equal the accepted OID")
    repository_result = _command_result(runner, ["gh", "repo", "view", "--json", "nameWithOwner"], root)
    if repository_result.returncode:
        _record_delivery_failure(run_dir, root, "github_repository_lookup_failed")
        raise HarnessError("GitHub repository lookup failed")
    try:
        repository = json.loads(repository_result.stdout)["nameWithOwner"]
        bounded_text(repository, "github.repository", maximum=240)
    except (json.JSONDecodeError, KeyError, TypeError, HarnessError) as exc:
        _record_delivery_failure(run_dir, root, "github_repository_response_invalid")
        raise HarnessError("GitHub repository lookup returned invalid metadata") from exc
    identity = {"repository": repository, "base_ref": base_ref, "head_ref": head_ref, "accepted_head_oid": oid, "initiative_marker": marker}

    def bind_identity(cp: dict[str, Any], _manifest: dict[str, Any], _method: Method) -> None:
        cp["delivery"]["intent"] = {"preflight": preflight, "identity": identity, "digest": digest_json(identity)}

    mutate(run_dir, root, "github_delivery_identity_bound", {"identity_digest": digest_json(identity)}, bind_identity)
    listing = _command_result(runner, ["gh", "pr", "list", "--head", head_ref, "--base", base_ref, "--state", "all", "--json", "number,url,state,headRefOid,body"], root)
    if listing.returncode:
        _record_delivery_failure(run_dir, root, "github_lookup_failed")
        raise HarnessError("GitHub pull-request lookup failed")
    try:
        candidates = json.loads(listing.stdout or "[]")
        if not isinstance(candidates, list):
            raise TypeError
    except (json.JSONDecodeError, TypeError) as exc:
        _record_delivery_failure(run_dir, root, "github_lookup_response_invalid")
        raise HarnessError("GitHub pull-request lookup returned invalid metadata") from exc
    match = next((item for item in candidates if item.get("headRefOid") == oid and marker in (item.get("body") or "")), None)
    if match is None and candidates:
        _record_delivery_failure(run_dir, root, "branch_identity_conflict")
        raise HarnessError("head/base branch is already associated with a different Initiative or OID")
    if match is None:
        created = _command_result(runner, ["gh", "pr", "create", "--base", base_ref, "--head", head_ref, "--title", manifest["title"], "--body", marker], root)
        if created.returncode:
            _record_delivery_failure(run_dir, root, "github_create_ambiguous")
            raise HarnessError("GitHub pull-request creation failed; retry will lookup before create")
        outcome = {"url": created.stdout.strip(), "state": "OPEN", "head_oid": oid, "reused": False}
    else:
        outcome = {"url": match["url"], "state": match["state"], "head_oid": oid, "reused": True}
    _crash_point("after_remote_delivery")

    def finish(cp: dict[str, Any], active_manifest: dict[str, Any], active_method: Method) -> None:
        cp["delivery"]["state"] = "delivered"
        cp["delivery"]["outcome"] = outcome
        _add_control_artifact(cp, active_manifest, active_method, "delivery_evidence", {"outcome": "delivered", "finding_ids": [], "summary_code": "github_pr"})
        _add_control_artifact(cp, active_manifest, active_method, "handoff", {"outcome": "delivered", "finding_ids": [], "summary_code": "handoff_ready"})

    mutate(run_dir, root, "github_delivery_outcome", {"state": outcome["state"], "reused": outcome["reused"]}, finish)
    return outcome


def _record_delivery_failure(run_dir: Path, root: Path, error_class: str) -> None:
    def change(cp: dict[str, Any], _manifest: dict[str, Any], _method: Method) -> None:
        cp["delivery"]["state"] = "failed"
        cp["delivery"]["outcome"] = {"error_class": error_class, "timestamp": now()}

    mutate(run_dir, root, "github_delivery_failed", {"error_class": error_class}, change)


def close_initiative(run_dir: Path, root: Path) -> None:
    manifest, checkpoint, method = _consistent_run(run_dir, root)
    if checkpoint.get("closed_at"):
        validate_acceptance_seal(checkpoint)
        return

    def change(cp: dict[str, Any], active_manifest: dict[str, Any], active_method: Method) -> None:
        if cp["current_stage"] != "closure" or cp["delivery"]["state"] != "delivered":
            raise HarnessError("closure requires delivered closure substate")
        if not cp.get("acceptance_seal"):
            raise HarnessError("closure requires an acceptance seal")
        validate_acceptance_seal(cp)
        stage = cp["stages"]["closure"]
        required = set(_required_outputs(active_method, "closure", active_manifest["route"]))
        kinds = {item["kind"] for item in _accepted_artifacts(cp) if item["stage"] == "closure"}
        if missing := sorted(required - kinds):
            raise HarnessError("closure lacks artifacts: " + ", ".join(missing))
        stage.update({"status": "passed", "resolved_at": now()})
        cp["closed_at"] = now()
        cp["current_stage"] = "closure"
        cp["seal_root_hash"] = digest_json({"manifest": active_manifest, "checkpoint": {key: value for key, value in cp.items() if key not in {"revision", "event_hash", "seal_root_hash"}}})

    mutate(run_dir, root, "initiative_closed", {}, change)


def validate_acceptance_seal(checkpoint: dict[str, Any]) -> None:
    seal = checkpoint.get("acceptance_seal")
    if not isinstance(seal, dict) or not seal.get("evidence_root_hash") or not seal.get("file_fingerprints"):
        raise HarnessError("acceptance seal is invalid")
    expected = digest_json({key: value for key, value in seal.items() if key != "evidence_root_hash"})
    if seal["evidence_root_hash"] != expected:
        raise HarnessError("acceptance seal root hash is invalid")
    accepted = {item["artifact_id"]: item["sha256"] for item in _accepted_artifacts(checkpoint)}
    if any(accepted.get(artifact_id) != sha256 for artifact_id, sha256 in seal.get("artifact_digests", [])):
        raise HarnessError("acceptance seal artifact digest is invalid")
    if seal.get("gates_digest") != digest_json(checkpoint["gates"]):
        raise HarnessError("acceptance seal gate digest is invalid")


def derive_metrics(run_dir: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    try:
        events = _read_events(run_dir / "events.jsonl")
    except HarnessError:
        events = []
    actions: dict[str, int] = {}
    for event in events:
        actions[event["action"]] = actions.get(event["action"], 0) + 1
    stage_durations: dict[str, int] = {}
    attempt_durations: dict[str, list[int]] = {}
    stage_records = [{"stage": stage_id, **stage} for stage_id, stage in checkpoint["stages"].items()] + checkpoint.get("attempt_history", [])
    for record in stage_records:
        stage_id = record["stage"]
        stage = record
        if stage.get("entered_at") and stage.get("resolved_at"):
            start = datetime.fromisoformat(stage["entered_at"])
            end = datetime.fromisoformat(stage["resolved_at"])
            duration = max(0, round((end - start).total_seconds() * 1000))
            attempt_durations.setdefault(stage_id, []).append(duration)
    stage_durations = {stage: sum(values) for stage, values in attempt_durations.items()}
    delta = gate_delta_from_checkpoint(checkpoint)
    baseline_files = checkpoint.get("baseline", {}).get("file_fingerprints", {}) if checkpoint.get("baseline") else {}
    accepted_files = checkpoint.get("acceptance_seal", {}).get("file_fingerprints", {}) if checkpoint.get("acceptance_seal") else {}
    changed_paths = sorted(path for path in set(baseline_files) | set(accepted_files) if baseline_files.get(path) != accepted_files.get(path)) if accepted_files else []
    gate_results = [record for phase in checkpoint["gates"].values() for record in phase.values()]
    started = datetime.fromisoformat(checkpoint["stages"]["initialization"]["entered_at"])
    ended_value = checkpoint.get("closed_at") or now()
    cycle_ms = max(0, round((datetime.fromisoformat(ended_value) - started).total_seconds() * 1000))
    return {
        "revision": checkpoint["revision"],
        "stage_duration_ms": stage_durations,
        "attempts": {stage: value["attempt"] for stage, value in checkpoint["stages"].items()},
        "rejections": actions.get("stage_rejected", 0),
        "circuit_breaker_active": "rejection_circuit_breaker" in checkpoint["blockers"],
        "rollbacks": [decision.get("rollback_target") for decision in checkpoint["decisions"] if decision["decision"] == "reject"],
        "agent_calls": checkpoint["usage"]["agent_calls"],
        "agent_call_overrides": checkpoint["usage"].get("agent_call_overrides", 0),
        "retries": dict(checkpoint["usage"]["retries"]),
        "retry_overrides": dict(checkpoint["usage"].get("retry_overrides", {})),
        "human_decisions": len(checkpoint["decisions"]),
        "gate_counts": {phase: len(values) for phase, values in checkpoint["gates"].items()},
        "gate_passes": sum(record["exit_code"] == 0 for record in gate_results),
        "gate_failures": sum(record["exit_code"] != 0 for record in gate_results),
        "new_gate_failures": len(delta["blockers"]),
        "pre_existing_failures": len(delta["pre_existing_failures"]),
        "soft_scars": len(delta["accepted_soft_scars"]),
        "delivery_state": checkpoint["delivery"]["state"],
        "delivery_attempts": checkpoint["delivery"]["attempts"],
        "delivery_reused": bool((checkpoint["delivery"].get("outcome") or {}).get("reused")),
        "delivery_succeeded": checkpoint["delivery"]["state"] == "delivered",
        "delivery_failed": checkpoint["delivery"]["state"] == "failed",
        "changed_paths": changed_paths,
        "changed_path_count": len(changed_paths),
        "scope_overflow_count": 0 if checkpoint.get("acceptance_seal") else None,
        "cycle_duration_ms": cycle_ms,
        "closed": bool(checkpoint.get("closed_at")),
    }


def handoff_record(manifest: dict[str, Any], checkpoint: dict[str, Any], method: Method, metrics: dict[str, Any]) -> dict[str, Any]:
    accepted = []
    for artifact in _accepted_artifacts(checkpoint):
        value = {key: artifact[key] for key in ("artifact_id", "kind", "storage_class", "path", "sha256", "control") if key in artifact}
        accepted.append(value)
    result = {
        "schema_version": RUN_SCHEMA,
        "initiative_id": manifest["initiative_id"],
        "title": manifest["title"],
        "route": manifest["route"],
        "spec": manifest["spec"],
        "objective_ref": manifest["objective_ref"],
        "method": {"version": method.version, "path": method.relative_path, "digests": method.digests},
        "revision": checkpoint["revision"],
        "current_stage": checkpoint["current_stage"],
        "blockers": checkpoint["blockers"],
        "accepted_artifacts": accepted,
        "gate_delta": gate_delta_from_checkpoint(checkpoint),
        "delivery": checkpoint["delivery"],
        "metrics": metrics,
        "acceptance_oid": checkpoint.get("acceptance_seal", {}).get("head") if checkpoint.get("acceptance_seal") else None,
    }
    reject_secrets(result, "handoff")
    return result


def project_context(run_dir: Path, root: Path) -> dict[str, Any]:
    manifest, checkpoint, method = _consistent_run(run_dir, root)
    registry = read_json(root / "specs" / "registry.json")
    related = []
    for owner in method.project_map["owners"]:
        if any(path.startswith(owner["prefix"]) for path in manifest["allowed_paths"]):
            related.append(owner)
    related_runs = []
    for candidate in sorted(path for path in run_dir.parent.iterdir() if path.is_dir() and path != run_dir):
        try:
            other_manifest, other_checkpoint, _ = _consistent_run(candidate, root)
        except HarnessError:
            continue
        if any(path_allowed(path.rstrip("/"), other_manifest["allowed_paths"]) or path_allowed(path.rstrip("/"), manifest["allowed_paths"]) for path in set(manifest["allowed_paths"]) & set(other_manifest["allowed_paths"])):
            related_runs.append({"initiative_id": other_manifest["initiative_id"], "current_stage": other_checkpoint["current_stage"], "closed": bool(other_checkpoint["closed_at"])})
    return {
        "schema_version": RUN_SCHEMA,
        "initiative_id": manifest["initiative_id"],
        "current_stage": checkpoint["current_stage"],
        "route": manifest["route"],
        "scope": manifest["allowed_paths"],
        "owners": related,
        "context_sources": method.project_map["context_sources"],
        "related_initiatives": related_runs,
        "specs": [record for record in registry["specs"] if record["id"] in {spec for owner in related for spec in owner["specs"]}],
        "accepted_artifacts": [{key: item[key] for key in ("artifact_id", "kind", "path", "sha256") if key in item} for item in _accepted_artifacts(checkpoint)],
        "git": {"branch": _git(root, "branch", "--show-current"), "head": _git(root, "rev-parse", "HEAD")},
    }


def portfolio(runs_root: Path, root: Path, *, include_metrics: bool = False) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    if not runs_root.exists():
        return {"schema_version": RUN_SCHEMA, "initiatives": []}
    for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        try:
            manifest, checkpoint, _ = _consistent_run(run_dir, root)
        except HarnessError:
            continue
        events = _read_events(run_dir / "events.jsonl")
        record = {"initiative_id": manifest["initiative_id"], "title": manifest["title"], "route": manifest["route"], "current_stage": checkpoint["current_stage"], "blockers": checkpoint["blockers"], "revision": checkpoint["revision"], "closed": bool(checkpoint["closed_at"]), "updated_at": events[-1]["timestamp"] if events else manifest["created_at"], "artifact_refs": [item["artifact_id"] for item in _accepted_artifacts(checkpoint)]}
        if include_metrics:
            record["metrics"] = derive_metrics(run_dir, checkpoint)
        runs.append(record)
    return {"schema_version": RUN_SCHEMA, "initiatives": runs}


def export_bundle(run_dir: Path, root: Path, output: Path) -> None:
    manifest, checkpoint, method = _consistent_run(run_dir, root)
    oid = checkpoint.get("acceptance_seal", {}).get("head") or _git(root, "rev-parse", "HEAD")
    remote_contains = _git(root, "branch", "-r", "--contains", oid, check=False)
    if not remote_contains:
        raise HarnessError("bundle export requires an OID reachable from a remote branch")
    for artifact in _accepted_artifacts(checkpoint):
        if artifact["storage_class"] != "repository_ref":
            continue
        result = subprocess.run(["git", "show", f"{oid}:{artifact['path']}"], cwd=root, capture_output=True, check=False)
        if result.returncode or digest_bytes(result.stdout) != artifact["sha256"]:
            raise HarnessError("accepted repository artifact is not reachable at the export OID")
    events = _read_events(run_dir / "events.jsonl")
    payload = {"schema_version": RUN_SCHEMA, "git_oid": oid, "manifest": manifest, "checkpoint": checkpoint, "events": events, "method": {"version": method.version, "path": method.relative_path, "digests": method.digests}}
    bundle = {**payload, "bundle_root_hash": digest_json(payload)}
    write_json_atomic(output, bundle)


def import_bundle(bundle_path: Path, runs_root: Path, root: Path) -> Path:
    bundle = read_json(bundle_path)
    root_hash = bundle.pop("bundle_root_hash", None)
    if root_hash != digest_json(bundle):
        raise HarnessError("bundle root hash is invalid")
    manifest = bundle["manifest"]
    checkpoint = bundle["checkpoint"]
    reject_secrets(bundle, "bundle")
    reject_private_paths(bundle, "bundle")
    if manifest.get("schema_version") != RUN_SCHEMA or checkpoint.get("schema_version") != RUN_SCHEMA:
        raise HarnessError("bundle schema is unsupported")
    if manifest.get("initiative_id") != checkpoint.get("initiative_id"):
        raise HarnessError("bundle Initiative IDs disagree")
    if checkpoint.get("manifest_digest") != digest_json(manifest):
        raise HarnessError("bundle manifest digest is invalid")
    if manifest.get("method") != bundle.get("method"):
        raise HarnessError("bundle method authorities disagree")
    events = bundle.get("events")
    if not isinstance(events, list):
        raise HarnessError("bundle event stream is invalid")
    _validate_event_chain(events)
    tail_revision = events[-1]["revision"] if events else 0
    tail_hash = events[-1]["event_hash"] if events else "0" * 64
    if checkpoint.get("revision") != tail_revision or checkpoint.get("event_hash") != tail_hash:
        raise HarnessError("bundle checkpoint and event tail disagree")
    if events:
        state = {key: value for key, value in checkpoint.items() if key != "event_hash"}
        if events[-1].get("payload_digest") != digest_json(state):
            raise HarnessError("bundle checkpoint payload is invalid")
    method = load_method(root, bundle["method"]["path"])
    if method.digests != bundle["method"]["digests"]:
        raise HarnessError("bundle method is unavailable")
    oid = bundle["git_oid"]
    if subprocess.run(["git", "cat-file", "-e", f"{oid}^{{commit}}"], cwd=root, capture_output=True, check=False).returncode:
        raise HarnessError("bundle Git OID is unavailable")
    for artifact in [item for item in checkpoint["artifacts"] if item["status"] == "accepted" and item["storage_class"] == "repository_ref"]:
        result = subprocess.run(["git", "show", f"{oid}:{artifact['path']}"], cwd=root, capture_output=True, check=False)
        if result.returncode or digest_bytes(result.stdout) != artifact["sha256"]:
            raise HarnessError("bundle artifact digest is unavailable")
    run_dir = run_directory(runs_root, manifest["initiative_id"])
    if run_dir.exists():
        raise HarnessError("bundle conflicts with a local Initiative ID")
    runs_root.mkdir(parents=True, exist_ok=True)
    temporary = runs_root / f".import-{manifest['initiative_id']}-{os.getpid()}"
    if temporary.exists():
        raise HarnessError("bundle import staging path already exists")
    temporary.mkdir()
    try:
        write_json_atomic(temporary / "manifest.json", manifest)
        write_json_atomic(temporary / "checkpoint.json", checkpoint)
        with (temporary / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _derive_views(temporary, manifest, checkpoint, method)
        os.replace(temporary, run_dir)
        _fsync_directory(runs_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return run_dir
