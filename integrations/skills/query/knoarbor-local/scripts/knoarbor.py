#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
RUNTIME_DIR_ENV = "KNOARBOR_RUNTIME_DIR"


def main() -> int:
    parser = argparse.ArgumentParser(description="Operate a local KnoArbor service from a host-AI skill.")
    parser.add_argument("--base-url", default=os.environ.get("KNOARBOR_BASE_URL"))
    parser.add_argument("--vault", default=os.environ.get("KNOARBOR_VAULT_PATH"))
    parser.add_argument("--vault-id", default=os.environ.get("KNOARBOR_VAULT_ID"))
    parser.add_argument("--config", default=os.environ.get("KNOARBOR_CONFIG_PATH"))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_check(subparsers)
    _add_doctor(subparsers)
    _add_query(subparsers)
    _add_page(subparsers)
    _add_sources(subparsers)
    _add_ingest(subparsers)
    _add_lint(subparsers)
    _add_runs(subparsers)
    _add_report(subparsers)

    args = parser.parse_args()
    runtime = _runtime(args)

    try:
        if args.command == "check":
            return _cmd_check(args, runtime)
        if args.command == "doctor":
            return _cmd_doctor(args, runtime)
        if args.command == "query":
            return _cmd_query(args, runtime)
        if args.command == "page":
            return _cmd_page(args, runtime)
        if args.command == "sources":
            return _cmd_sources(args, runtime)
        if args.command == "ingest":
            return _cmd_ingest(args, runtime)
        if args.command == "lint":
            return _cmd_lint(args, runtime)
        if args.command == "runs":
            return _cmd_runs(args, runtime)
        if args.command == "report":
            return _cmd_report(args, runtime)
    except urllib.error.HTTPError as exc:
        print(_format_http_error(exc), file=sys.stderr)
        print(f"Check whether the service is running at {runtime.base_url}/health.", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"KnoArbor request failed: {exc}", file=sys.stderr)
        print(f"Check whether the service is running at {runtime.base_url}/health.", file=sys.stderr)
        return 1
    return 2


class Runtime:
    def __init__(
        self,
        *,
        base_url: str,
        vault_path: str | None,
        config_path: Path | None,
        timeout: float,
        output_format: str,
        vault_id: str | None = None,
        vault_name: str | None = None,
        vaults: list[dict[str, str]] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.vault_path = vault_path
        self.config_path = config_path
        self.timeout = timeout
        self.output_format = output_format
        self.vault_id = vault_id
        self.vault_name = vault_name
        self.vaults = vaults or []


def _runtime(args: argparse.Namespace) -> Runtime:
    config_path = _resolve_config_path(args.config)
    config = _load_yaml(config_path) if config_path else {}
    endpoint = _runtime_endpoint_data(config_path) if config_path else _user_runtime_endpoint_data()
    base_url = args.base_url or _base_url_from_runtime_endpoint(endpoint) or _base_url_from_config(config) or DEFAULT_BASE_URL
    vaults = _vaults_from_runtime_endpoint(endpoint) or _vaults_from_config(config, config_path)
    arg_vault_id = getattr(args, "vault_id", None)
    requested_vault_id = arg_vault_id.strip() if arg_vault_id else None
    selected_vault_path = _vault_path_for_id(vaults, requested_vault_id)
    vault_path = args.vault or selected_vault_path or (None if requested_vault_id else _vault_path_from_runtime_endpoint(endpoint) or _vault_path_from_config(config, config_path))
    vault_id = _vault_id_from_runtime_endpoint(endpoint)
    vault_name = _vault_name_from_runtime_endpoint(endpoint)
    if requested_vault_id:
        vault_id = requested_vault_id
        vault_name = _vault_name_for_id(vaults, requested_vault_id) or vault_name
    if not args.vault and not requested_vault_id:
        vault_id = vault_id or _vault_id_from_config(config)
        vault_name = vault_name or _vault_name_from_config(config)
    if config_path is None:
        config_path = _config_path_from_runtime_context(endpoint)
    if not vault_path:
        runtime_context = _runtime_context_from_service(base_url, args.timeout)
        runtime_vaults = _vaults_from_runtime_endpoint(runtime_context)
        selected_vault_path = _vault_path_for_id(runtime_vaults, requested_vault_id)
        vault_path = selected_vault_path or (None if requested_vault_id else _vault_path_from_runtime_endpoint(runtime_context))
        vault_id = vault_id or _vault_id_from_runtime_endpoint(runtime_context)
        vault_name = vault_name or _vault_name_from_runtime_endpoint(runtime_context)
        vaults = vaults or runtime_vaults
        if requested_vault_id:
            vault_id = requested_vault_id
            vault_name = _vault_name_for_id(vaults, requested_vault_id) or vault_name
        if config_path is None:
            config_path = _config_path_from_runtime_context(runtime_context)
    return Runtime(
        base_url=base_url,
        vault_path=vault_path,
        config_path=config_path,
        timeout=args.timeout,
        output_format=args.format,
        vault_id=vault_id,
        vault_name=vault_name,
        vaults=vaults,
    )


def _add_check(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    subparsers.add_parser("check", help="Check service connectivity and resolved configuration.")


def _add_doctor(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("doctor", help="Run KnoArbor diagnostics.")
    parser.add_argument("--connector", action="append", default=[])


def _add_query(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("query", help="Retrieve wiki context for a user question.")
    parser.add_argument("query")
    parser.add_argument("--mode", choices=["quick", "balanced", "deep"], default="balanced")
    parser.add_argument("--context-format", choices=["compact", "full"], default="compact")
    parser.add_argument("--max-results", type=int, default=6)
    parser.add_argument("--page-dir", action="append", dest="page_dirs", default=[])
    parser.add_argument("--include-related", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-content", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--all-vaults", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--query-vault-id", action="append", dest="query_vault_ids", default=[], help="Search a configured vault ID. Repeat to search multiple vaults.")
    parser.add_argument("--auto", action=argparse.BooleanOptionalAction, default=True)


def _add_page(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("page", help="List, read, or inspect wiki pages.")
    page_sub = parser.add_subparsers(dest="page_command", required=True)
    list_parser = page_sub.add_parser("list", help="List wiki pages.")
    list_parser.add_argument("--dir", dest="page_dir", default=None)
    list_parser.add_argument("--contains", default=None)
    read_parser = page_sub.add_parser("read", help="Read one wiki page by path.")
    read_parser.add_argument("path")
    links_parser = page_sub.add_parser("links", help="Read outbound links and backlinks for one page.")
    links_parser.add_argument("path")


def _add_sources(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("sources", help="Inspect supported source connectors.")
    source_sub = parser.add_subparsers(dest="sources_command", required=True)
    catalog = source_sub.add_parser("catalog", help="Read the source connector capability catalog.")
    catalog.add_argument("--connector", action="append", default=[])


def _add_ingest(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("ingest", help="Start a wiki ingest run.")
    ingest_sub = parser.add_subparsers(dest="ingest_command", required=True)
    connector = ingest_sub.add_parser("connector", help="Ingest one or more configured connectors.")
    connector.add_argument("names", nargs="*", help="Connector names such as codex, markdown, claude_code.")
    connector.add_argument("--all", action="store_true", help="Run all enabled connectors.")
    _add_workflow_flags(connector)
    file_parser = ingest_sub.add_parser("file", help="Ingest one local file path.")
    file_parser.add_argument("path")
    _add_workflow_flags(file_parser)
    folder_parser = ingest_sub.add_parser("folder", help="Ingest one local folder path without changing persistent configuration.")
    folder_parser.add_argument("path")
    folder_parser.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True)
    _add_workflow_flags(folder_parser)
    recovery = ingest_sub.add_parser("recovery", help="Retry failed ingest items from a prior run.")
    recovery.add_argument("run_id")
    _add_workflow_flags(recovery)


def _add_lint(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("lint", help="Start a wiki lint/maintenance run.")
    parser.add_argument("--mode", choices=["deterministic", "structural", "quality", "full", "semantic_structural", "semantic_quality", "semantic_full"], default="semantic_structural")
    parser.add_argument("--profile", choices=["standard", "deep"], default="standard")
    parser.add_argument("--scope-page", action="append", dest="scope_pages", default=[])
    parser.add_argument("--apply-safe-fixes", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--auto-apply-reviewed", action=argparse.BooleanOptionalAction, default=True)
    _add_workflow_flags(parser)


def _add_runs(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("runs", help="Inspect or cancel workflow runs.")
    run_sub = parser.add_subparsers(dest="runs_command", required=True)
    list_parser = run_sub.add_parser("list", help="List recent runs.")
    list_parser.add_argument("--active-only", action=argparse.BooleanOptionalAction, default=False)
    list_parser.add_argument("--limit", type=int, default=10)
    list_parser.add_argument("--all-vaults", action=argparse.BooleanOptionalAction, default=False)
    get_parser = run_sub.add_parser("get", help="Read one run record.")
    get_parser.add_argument("run_id")
    events_parser = run_sub.add_parser("events", help="Read run events.")
    events_parser.add_argument("run_id")
    events_parser.add_argument("--after", type=int, default=0)
    events_parser.add_argument("--limit", type=int, default=50)
    cancel_parser = run_sub.add_parser("cancel", help="Request cancellation for one run.")
    cancel_parser.add_argument("run_id")


def _add_report(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("report", help="List or read workflow reports.")
    report_sub = parser.add_subparsers(dest="report_command", required=True)
    list_parser = report_sub.add_parser("list", help="List reports.")
    list_parser.add_argument("--all-vaults", action=argparse.BooleanOptionalAction, default=False)
    read_parser = report_sub.add_parser("read", help="Read one report by maintenance path.")
    read_parser.add_argument("path")


def _add_workflow_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--execution", choices=["queued", "direct"], default="queued")
    parser.add_argument("--write", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--append-ledger", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--max-tokens", type=int, default=None)


def _cmd_check(args: argparse.Namespace, runtime: Runtime) -> int:
    result: dict[str, Any] = {
        "schema_version": "knoarbor_skill_check.v1",
        "base_url": runtime.base_url,
        "config_path": str(runtime.config_path) if runtime.config_path else None,
        "vault_path": str(Path(runtime.vault_path).expanduser()) if runtime.vault_path else None,
        "vault_id": runtime.vault_id,
        "vault_name": runtime.vault_name,
        "vaults": runtime.vaults,
        "service_online": False,
        "health": None,
        "errors": [],
    }
    try:
        result["health"] = _get_json(f"{runtime.base_url}/health", timeout=runtime.timeout)
        result["service_online"] = True
    except urllib.error.URLError as exc:
        result["errors"].append(f"KnoArbor service unavailable: {exc}")
    if not runtime.vault_path:
        result["errors"].append("Vault path is not configured.")
    _print_or_format(result, runtime, formatter=_format_check)
    return 0 if result["service_online"] and runtime.vault_path else 1


def _cmd_doctor(args: argparse.Namespace, runtime: Runtime) -> int:
    query: dict[str, Any] = {}
    if runtime.config_path:
        query["config_path"] = str(runtime.config_path)
    for connector in args.connector:
        query.setdefault("connector", []).append(connector)
    response = _get_json(_url(runtime.base_url, "/doctor", query), timeout=runtime.timeout)
    return _print_or_format(response, runtime, formatter=_format_doctor)


def _cmd_query(args: argparse.Namespace, runtime: Runtime) -> int:
    vault_path = runtime.vault_path if args.all_vaults or args.query_vault_ids else _require_vault(runtime)
    settings = _query_settings(args)
    payload = {
        "query": args.query,
        "vault_path": vault_path,
        "vault_id": runtime.vault_id,
        "vault_ids": args.query_vault_ids,
        "all_vaults": args.all_vaults,
        "config_path": str(runtime.config_path) if runtime.config_path else None,
        "mode": settings["mode"],
        "context_format": settings["context_format"],
        "max_results": settings["max_results"],
        "page_dirs": args.page_dirs,
        "include_related": args.include_related,
        "include_content": settings["include_content"],
        "caller": "generic-skill",
    }
    response = _post_json(f"{runtime.base_url}/query", payload, timeout=runtime.timeout)
    return _print_or_format(response, runtime, formatter=_format_query)


def _cmd_page(args: argparse.Namespace, runtime: Runtime) -> int:
    vault_path = _require_vault(runtime)
    if args.page_command == "list":
        response = _get_json(_url(runtime.base_url, "/wiki/pages", _vault_query(runtime, {"vault_path": vault_path})), timeout=runtime.timeout)
        pages = response.get("pages", [])
        if args.page_dir:
            pages = [page for page in pages if page.get("directory") == args.page_dir]
        if args.contains:
            needle = args.contains.lower()
            pages = [page for page in pages if needle in f"{page.get('title', '')} {page.get('path', '')}".lower()]
        response = {**response, "pages": pages}
        return _print_or_format(response, runtime, formatter=_format_page_list)
    if args.page_command == "read":
        response = _get_json(_url(runtime.base_url, "/wiki/pages/content", _vault_query(runtime, {"vault_path": vault_path, "path": args.path})), timeout=runtime.timeout)
        return _print_or_format(response, runtime, formatter=_format_page_read)
    if args.page_command == "links":
        response = _get_json(_url(runtime.base_url, "/wiki/pages/links", _vault_query(runtime, {"vault_path": vault_path, "path": args.path})), timeout=runtime.timeout)
        return _print_or_format(response, runtime, formatter=_format_page_links)
    return 2


def _cmd_sources(args: argparse.Namespace, runtime: Runtime) -> int:
    if args.sources_command == "catalog":
        query: dict[str, Any] = {}
        if runtime.config_path:
            query["config_path"] = str(runtime.config_path)
        if args.connector:
            query["connector"] = args.connector
        response = _get_json(_url(runtime.base_url, "/sources", query), timeout=runtime.timeout)
        return _print_or_format(response, runtime, formatter=_format_sources_catalog)
    return 2


def _cmd_ingest(args: argparse.Namespace, runtime: Runtime) -> int:
    payload = _workflow_payload(args, runtime)
    payload["vault_path"] = _require_vault(runtime)
    payload["vault_id"] = runtime.vault_id
    if args.ingest_command == "connector":
        payload["kind"] = "connectors"
        if not args.all and args.names:
            payload["connector_names"] = args.names
    elif args.ingest_command == "file":
        payload["kind"] = "file"
        payload["input_path"] = args.path
    elif args.ingest_command == "folder":
        payload["kind"] = "folder"
        payload["input_path"] = args.path
        payload["recursive"] = args.recursive
    elif args.ingest_command == "recovery":
        payload["kind"] = "recovery"
        payload["recovery_of_run_id"] = args.run_id
        payload["recovery_vault_path"] = _require_vault(runtime)
    response = _post_json(f"{runtime.base_url}/ingest", payload, timeout=runtime.timeout)
    return _print_or_format(response, runtime, formatter=_format_workflow)


def _cmd_lint(args: argparse.Namespace, runtime: Runtime) -> int:
    vault_path = _require_vault(runtime)
    payload = _workflow_payload(args, runtime)
    payload.update(
        {
            "vault_path": vault_path,
            "vault_id": runtime.vault_id,
            "mode": args.mode,
            "profile": args.profile,
            "apply_safe_fixes": args.apply_safe_fixes,
            "auto_apply_reviewed_changes": args.auto_apply_reviewed,
            "scope": {
                "schema_version": "maintenance_scope.v1",
                "scope_id": f"skill:{int(time.time())}",
                "trigger": "manual",
                "source": {"kind": "skill"},
                "changed_pages": args.scope_pages,
                "recommended_lint_modes": [args.mode],
                "reason": "Manual maintenance run from KnoArbor skill.",
            },
        }
    )
    response = _post_json(f"{runtime.base_url}/lint", payload, timeout=runtime.timeout)
    return _print_or_format(response, runtime, formatter=_format_workflow)


def _cmd_runs(args: argparse.Namespace, runtime: Runtime) -> int:
    if args.runs_command == "list":
        vault_path = runtime.vault_path if args.all_vaults else _require_vault(runtime)
        response = _get_json(
            _url(
                runtime.base_url,
                "/runs",
                {
                    "vault_path": vault_path,
                    "vault_id": runtime.vault_id,
                    "config_path": str(runtime.config_path) if runtime.config_path else None,
                    "all_vaults": str(args.all_vaults).lower(),
                    "active_only": str(args.active_only).lower(),
                    "limit": args.limit,
                },
            ),
            timeout=runtime.timeout,
        )
        return _print_or_format(response, runtime, formatter=_format_runs)
    vault_path = _require_vault(runtime)
    if args.runs_command == "get":
        response = _get_json(_url(runtime.base_url, f"/runs/{args.run_id}", _vault_query(runtime, {"vault_path": vault_path})), timeout=runtime.timeout)
        return _print_or_format(response, runtime, formatter=_format_run)
    if args.runs_command == "events":
        response = _get_json(
            _url(runtime.base_url, f"/runs/{args.run_id}/events", _vault_query(runtime, {"vault_path": vault_path, "after": args.after, "limit": args.limit})),
            timeout=runtime.timeout,
        )
        return _print_or_format(response, runtime, formatter=_format_run_events)
    if args.runs_command == "cancel":
        response = _post_json(_url(runtime.base_url, f"/runs/{args.run_id}/cancel", _vault_query(runtime, {"vault_path": vault_path})), {}, timeout=runtime.timeout)
        return _print_or_format(response, runtime, formatter=_format_run)
    return 2


def _cmd_report(args: argparse.Namespace, runtime: Runtime) -> int:
    if args.report_command == "list":
        vault_path = runtime.vault_path if args.all_vaults else _require_vault(runtime)
        response = _get_json(
            _url(
                runtime.base_url,
                "/reports",
                {
                    "vault_path": vault_path,
                    "vault_id": runtime.vault_id,
                    "config_path": str(runtime.config_path) if runtime.config_path else None,
                    "all_vaults": str(args.all_vaults).lower(),
                },
            ),
            timeout=runtime.timeout,
        )
        return _print_or_format(response, runtime, formatter=_format_reports)
    vault_path = _require_vault(runtime)
    if args.report_command == "read":
        response = _get_json(_url(runtime.base_url, "/reports/content", _vault_query(runtime, {"vault_path": vault_path, "path": args.path})), timeout=runtime.timeout)
        return _print_or_format(response, runtime, formatter=_format_report)
    return 2


def _vault_query(runtime: Runtime, query: dict[str, Any]) -> dict[str, Any]:
    payload = dict(query)
    if runtime.vault_id:
        payload["vault_id"] = runtime.vault_id
    if runtime.config_path:
        payload["config_path"] = str(runtime.config_path)
    return payload


def _workflow_payload(args: argparse.Namespace, runtime: Runtime) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "execution": args.execution,
        "write": args.write,
        "write_report": args.write_report,
        "append_ledger": args.append_ledger,
    }
    if runtime.config_path:
        payload["config_path"] = str(runtime.config_path)
    if args.provider:
        payload["provider"] = args.provider
    if args.max_tokens:
        payload["max_tokens"] = args.max_tokens
    return payload


def _resolve_config_path(value: str | None) -> Path | None:
    for candidate in _config_candidates(value):
        if candidate.exists():
            return candidate.resolve()
    return None


def _config_candidates(value: str | None) -> list[Path]:
    candidates: list[Path] = []
    if value:
        candidates.append(Path(value).expanduser())
    candidates.append(Path.cwd() / "config.yaml")
    return candidates


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        import yaml
    except ImportError:
        return _load_minimal_yaml(path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _load_minimal_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    section: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            section = line[:-1].strip()
            data.setdefault(section, {})
            continue
        if section and raw_line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            data.setdefault(section, {})[key.strip()] = value.strip().strip("'\"")
    return data


def _base_url_from_config(config: dict[str, Any]) -> str | None:
    server = config.get("server")
    if not isinstance(server, dict):
        return None
    host = server.get("host") or "127.0.0.1"
    port = server.get("port") or 8000
    return f"http://{host}:{port}"


def _runtime_endpoint_data(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {}
    endpoint_path = config_path.parent / ".knoarbor" / "endpoint.json"
    if not endpoint_path.exists():
        return {}
    try:
        data = json.loads(endpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _user_runtime_endpoint_data() -> dict[str, Any]:
    endpoint_path = _user_runtime_endpoint_path()
    if not endpoint_path.exists():
        return {}
    try:
        data = json.loads(endpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _user_runtime_endpoint_path() -> Path:
    runtime_dir = os.environ.get(RUNTIME_DIR_ENV)
    if runtime_dir:
        return Path(runtime_dir).expanduser().resolve() / "endpoint.json"
    return Path.home() / ".knoarbor" / "endpoint.json"


def _runtime_context_from_service(base_url: str, timeout: float) -> dict[str, Any]:
    try:
        return _get_json(f"{base_url.rstrip('/')}/runtime", timeout=timeout)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return {}


def _base_url_from_runtime_endpoint(data: dict[str, Any]) -> str | None:
    base_url = data.get("base_url")
    return str(base_url).strip() if base_url else None


def _vault_path_from_runtime_endpoint(data: dict[str, Any]) -> str | None:
    vault_path = data.get("vault_path")
    if not vault_path:
        return None
    return str(Path(str(vault_path)).expanduser())


def _vault_id_from_runtime_endpoint(data: dict[str, Any]) -> str | None:
    vault_id = data.get("vault_id")
    return str(vault_id).strip() if vault_id else None


def _vault_name_from_runtime_endpoint(data: dict[str, Any]) -> str | None:
    vault_name = data.get("vault_name")
    return str(vault_name).strip() if vault_name else None


def _vaults_from_runtime_endpoint(data: dict[str, Any]) -> list[dict[str, str]]:
    vaults = data.get("vaults")
    if not isinstance(vaults, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in vaults:
        if not isinstance(item, dict):
            continue
        vault_id = item.get("id")
        name = item.get("name")
        path = item.get("path")
        if vault_id and name and path:
            normalized.append({"id": str(vault_id), "name": str(name), "path": str(path)})
    return normalized


def _config_path_from_runtime_context(data: dict[str, Any]) -> Path | None:
    config_path = data.get("config_path")
    if not config_path:
        return None
    return Path(str(config_path)).expanduser()


def _vault_path_from_config(config: dict[str, Any], config_path: Path | None) -> str | None:
    vaults = config.get("vaults")
    if isinstance(vaults, dict) and isinstance(vaults.get("profiles"), dict):
        default_id = str(vaults.get("default") or "default")
        profile = vaults["profiles"].get(default_id)
        if isinstance(profile, dict) and profile.get("path"):
            return _resolve_config_path_value(profile["path"], config_path)
    vault = config.get("vault")
    if not isinstance(vault, dict) or not vault.get("path"):
        return None
    return _resolve_config_path_value(vault["path"], config_path)


def _vault_id_from_config(config: dict[str, Any]) -> str | None:
    vaults = config.get("vaults")
    if not isinstance(vaults, dict):
        return "default" if _vault_path_from_config(config, None) else None
    default_id = vaults.get("default")
    return str(default_id).strip() if default_id else None


def _vault_name_from_config(config: dict[str, Any]) -> str | None:
    vault_id = _vault_id_from_config(config)
    vaults = config.get("vaults")
    if not vault_id or not isinstance(vaults, dict) or not isinstance(vaults.get("profiles"), dict):
        project = config.get("project")
        return str(project["name"]).strip() if isinstance(project, dict) and project.get("name") else None
    profile = vaults["profiles"].get(vault_id)
    if not isinstance(profile, dict):
        return None
    name = profile.get("name")
    return str(name).strip() if name else None


def _vaults_from_config(config: dict[str, Any], config_path: Path | None) -> list[dict[str, str]]:
    vaults = config.get("vaults")
    if not isinstance(vaults, dict) or not isinstance(vaults.get("profiles"), dict):
        vault_path = _vault_path_from_config(config, config_path)
        if not vault_path:
            return []
        project = config.get("project")
        name = str(project.get("name") or "Default") if isinstance(project, dict) else "Default"
        return [{"id": "default", "name": name, "path": vault_path}]
    result: list[dict[str, str]] = []
    for vault_id, profile in vaults["profiles"].items():
        if not isinstance(profile, dict) or not profile.get("path"):
            continue
        result.append(
            {
                "id": str(vault_id),
                "name": str(profile.get("name") or vault_id),
                "path": _resolve_config_path_value(profile["path"], config_path),
            }
        )
    return result


def _vault_path_for_id(vaults: list[dict[str, str]], vault_id: str | None) -> str | None:
    if not vault_id:
        return None
    for item in vaults:
        if item.get("id") == vault_id:
            return item.get("path")
    return None


def _vault_name_for_id(vaults: list[dict[str, str]], vault_id: str | None) -> str | None:
    if not vault_id:
        return None
    for item in vaults:
        if item.get("id") == vault_id:
            return item.get("name")
    return None


def _resolve_config_path_value(value: object, config_path: Path | None) -> str:
    path = Path(str(value)).expanduser()
    if not path.is_absolute() and config_path:
        path = config_path.parent / path
    return str(path.resolve())


def _require_vault(runtime: Runtime) -> str:
    if not runtime.vault_path:
        print("KnoArbor vault path is required. Run `check`, pass --vault/--vault-id, or use a service that exposes /runtime.", file=sys.stderr)
        raise SystemExit(2)
    return str(Path(runtime.vault_path).expanduser())


def _query_settings(args: argparse.Namespace) -> dict[str, Any]:
    settings = {
        "mode": args.mode,
        "context_format": args.context_format,
        "max_results": args.max_results,
        "include_content": args.include_content,
    }
    if not args.auto:
        return settings
    query = args.query.lower()
    explicit_full = _contains_any(
        query,
        ["全文", "完整内容", "完整页面", "完整正文", "逐段", "原文", "详细页面", "full content", "full page", "entire page", "full text", "verbatim", "line by line", "section by section"],
    )
    broad_recall = _contains_any(query, ["尽量完整", "全部相关", "所有相关", "全面召回", "完整召回", "as much as possible", "all relevant", "comprehensive", "exhaustive"])
    detailed = _contains_any(query, ["详细", "深入", "展开", "分析", "对比", "方案", "架构", "为什么", "如何", "detail", "deep dive", "analyze", "compare", "architecture", "why", "how"])
    short_lookup = len(query.strip()) <= 32 and not detailed and not broad_recall and not explicit_full
    if explicit_full:
        settings["mode"] = "deep"
        settings["context_format"] = "full"
        settings["include_content"] = True
    elif detailed:
        settings["mode"] = "deep"
    if broad_recall:
        settings["mode"] = "deep"
        settings["max_results"] = max(settings["max_results"], 10)
    elif short_lookup:
        settings["max_results"] = min(settings["max_results"], 4)
    return settings


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _url(base_url: str, path: str, query: dict[str, Any] | None = None) -> str:
    if not query:
        return f"{base_url}{path}"
    pairs: list[tuple[str, str]] = []
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, list):
            pairs.extend((key, str(item)) for item in value)
        else:
            pairs.append((key, str(value)))
    return f"{base_url}{path}?{urllib.parse.urlencode(pairs)}"


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _format_http_error(exc: urllib.error.HTTPError) -> str:
    status = f"HTTP {exc.code}"
    try:
        raw_body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        raw_body = ""
    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    error = payload.get("error")
    lines = [f"KnoArbor request failed: {status}"]
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message") or exc.reason
        lines.append(f"[{code}] {message}" if code else str(message))
        if error.get("hint"):
            lines.append(f"hint: {error['hint']}")
        details = error.get("details")
        if details:
            lines.append(f"details: {json.dumps(details, ensure_ascii=False)}" if not isinstance(details, str) else f"details: {details}")
    elif payload.get("detail"):
        lines.append(str(payload["detail"]))
    elif raw_body:
        lines.append(raw_body.strip())
    else:
        lines.append(str(exc.reason))
    return "\n".join(lines)


def _print_or_format(response: dict[str, Any], runtime: Runtime, *, formatter) -> int:
    if runtime.output_format == "json":
        print(json.dumps(response, ensure_ascii=False, indent=2))
    else:
        print(formatter(response))
    return 0


def _format_check(response: dict[str, Any]) -> str:
    lines = [
        f"KnoArbor base URL: {response.get('base_url')}",
        f"Config path: {response.get('config_path') or 'not found'}",
        f"Vault: {response.get('vault_name') or response.get('vault_id') or 'unknown'}",
        f"Vault ID: {response.get('vault_id') or 'unknown'}",
        f"Vault path: {response.get('vault_path') or 'not configured'}",
        f"Service online: {'yes' if response.get('service_online') else 'no'}",
    ]
    vaults = response.get("vaults")
    if isinstance(vaults, list) and vaults:
        lines.append("Available vaults: " + ", ".join(str(item.get("name") or item.get("id") or item.get("path")) for item in vaults if isinstance(item, dict)))
    lines.extend(f"Error: {error}" for error in response.get("errors", []))
    return "\n".join(lines)


def _format_doctor(response: dict[str, Any]) -> str:
    checks = response.get("checks", [])
    counts = {"ok": 0, "warning": 0, "error": 0}
    for check in checks:
        status = str(check.get("status", ""))
        if status in counts:
            counts[status] += 1
    summary = response.get("summary")
    if isinstance(summary, dict):
        counts.update({key: int(summary.get(key, counts[key]) or 0) for key in counts})
    lines = [f"Doctor: {counts['ok']} ok, {counts['warning']} warning, {counts['error']} error"]
    for check in checks[:20]:
        lines.append(f"- [{check.get('status')}] {check.get('name')}: {check.get('message')}")
    return "\n".join(lines)


def _format_query(response: dict[str, Any]) -> str:
    stats = response.get("stats") if isinstance(response.get("stats"), dict) else {}
    vault_label = stats.get("vault_name") or stats.get("vault_id") or stats.get("vault_path") or "unknown"
    if stats.get("vault_path") and vault_label != stats.get("vault_path"):
        vault_label = f"{vault_label} ({stats.get('vault_path')})"
    lines = [f"Query: {response.get('query', '')}", f"Vault: {vault_label}", f"Retrieval mode: {response.get('retrieval_mode', '')}", "", "Results:"]
    for index, result in enumerate(response.get("results", [])[:10], start=1):
        vault_label = result.get("vault_name") or result.get("vault_id") or result.get("vault_path")
        prefix = f"{vault_label} · " if vault_label else ""
        lines.append(f"{index}. {prefix}{result.get('title', '')} ({result.get('path', '')}) [{result.get('relevance', '')}, {result.get('match_kind', '')}]")
        if result.get("summary"):
            lines.append(f"   {result['summary']}")
        for point in result.get("key_points", [])[:3]:
            lines.append(f"   - {point}")
        if result.get("content"):
            lines.append("   Content:")
            lines.append(_indent(str(result["content"])[:8000], "   "))
    if response.get("gaps"):
        lines.extend(["", "Gaps:", *[f"- {gap}" for gap in response["gaps"]]])
    if response.get("context_pack"):
        lines.extend(["", "Context Pack:", str(response["context_pack"])])
    return "\n".join(lines)


def _format_page_list(response: dict[str, Any]) -> str:
    pages = response.get("pages", [])
    lines = [f"Pages: {len(pages)}"]
    for page in pages[:80]:
        lines.append(f"- {page.get('title')} ({page.get('path')}) [{page.get('directory')}]")
    return "\n".join(lines)


def _format_page_read(response: dict[str, Any]) -> str:
    summary = response.get("summary", {})
    lines = [f"{summary.get('title') or response.get('path')}", str(response.get("path", "")), ""]
    lines.append(str(response.get("content", "")))
    return "\n".join(lines)


def _format_page_links(response: dict[str, Any]) -> str:
    lines = [f"Page links: {response.get('path')}", "", "Outbound links:"]
    for link in response.get("outbound_links", []):
        lines.append(f"- {link.get('target_path') or link.get('target')} ({'resolved' if link.get('resolved') else 'unresolved'})")
    lines.append("")
    lines.append("Backlinks:")
    for link in response.get("backlinks", []):
        lines.append(f"- {link.get('source')}")
    return "\n".join(lines)


def _format_sources_catalog(response: dict[str, Any]) -> str:
    connectors = response.get("connectors", [])
    lines = [f"Source connectors: {len(connectors)}"]
    for item in connectors:
        flags = []
        if item.get("enabled"):
            flags.append("enabled")
        elif item.get("configured"):
            flags.append("configured")
        if item.get("supports_checkpoint"):
            flags.append("checkpoint")
        if item.get("supports_segmentation_hint"):
            flags.append("segmentation")
        if item.get("requires_external_service"):
            flags.append("external")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        source_types = ", ".join(str(value) for value in item.get("source_types", [])) or "none"
        lines.append(f"- {item.get('name')} ({item.get('version')}) -> {source_types}{suffix}")
    return "\n".join(lines)


def _format_workflow(response: dict[str, Any]) -> str:
    lines = [f"{response.get('flow')} {response.get('execution')}: {response.get('status')}"]
    if response.get("run_id"):
        lines.append(f"Run ID: {response['run_id']}")
    run = response.get("run") or {}
    if run.get("report_path"):
        lines.append(f"Report: {run['report_path']}")
    if response.get("result"):
        result = response["result"]
        if isinstance(result, dict):
            for key in ["report_path", "written_pages", "applied_operations", "warnings"]:
                if key in result:
                    lines.append(f"{key}: {result[key]}")
    return "\n".join(lines)


def _format_runs(response: dict[str, Any]) -> str:
    runs = response.get("runs", [])
    lines = [f"Runs: {len(runs)}"]
    for run in runs:
        vault_label = run.get("vault_name") or run.get("vault_id") or run.get("vault_path") or "unknown"
        lines.append(f"- {vault_label} · {run.get('run_id')} {run.get('flow')} {run.get('status')} stage={run.get('stage')} report={run.get('report_path') or '-'}")
    return "\n".join(lines)


def _format_run(response: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Run ID: {response.get('run_id')}",
            f"Flow: {response.get('flow')}",
            f"Status: {response.get('status')}",
            f"Stage: {response.get('stage')}",
            f"Progress: {response.get('progress')}",
            f"Report: {response.get('report_path') or '-'}",
            f"Message: {response.get('message') or '-'}",
        ]
    )


def _format_run_events(response: dict[str, Any]) -> str:
    events = response.get("events", [])
    lines = [f"Events: {len(events)}"]
    for event in events:
        lines.append(f"- {event.get('sequence')} {event.get('stage')} {event.get('status')}: {event.get('message')}")
    return "\n".join(lines)


def _format_reports(response: dict[str, Any]) -> str:
    reports = response.get("reports", [])
    lines = [f"Reports: {len(reports)}"]
    for report in reports[:80]:
        vault_label = report.get("vault_name") or report.get("vault_id") or report.get("vault_path") or "unknown"
        lines.append(f"- {vault_label} · {report.get('kind')} {report.get('title')} {report.get('updated')} {report.get('path')}")
    return "\n".join(lines)


def _format_report(response: dict[str, Any]) -> str:
    return str(response.get("content", ""))


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
