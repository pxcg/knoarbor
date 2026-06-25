from __future__ import annotations

import argparse
import sys
from importlib.resources import files
from pathlib import Path

from knoarbor.core.schemas.maintenance import MaintenanceScope, MaintenanceScopeSource
from knoarbor.core.schemas.wiki_lint import LintRunRequest, WikiLintCandidateSelectRequest, WikiLintRequest, WikiScanRequest
from knoarbor.core.schemas.wiki_query import WikiQueryFeedbackRequest, WikiSearchRequest
from knoarbor.core.schemas.ingest_run import IngestFileRunRequest, IngestFolderRunRequest, IngestRecoveryRunRequest, IngestRunRequest
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.vaults import select_config_vault
from knoarbor.pipelines.source import SourcePipeline
from knoarbor.pipelines.ingest import IngestPipeline
from knoarbor.pipelines.ingest_context import IngestContextProvider
from knoarbor.services.doctor import DoctorService
from knoarbor.services.wiki_search import WikiSearchService
from knoarbor.services.ingest import IngestService
from knoarbor.services.run_manager import RunManager
from knoarbor.services.source_catalog import SourceCatalogService
from knoarbor.services.vault_registry import VaultRegistryService
from knoarbor.services.wiki_linter import WikiLinterService
from knoarbor.services.wiki_pages import WikiPageService
from knoarbor.services.wiki_reports import WikiReportService
from knoarbor.storage.wiki_index import machine_index_dir
from knoarbor.pipelines.lint import WikiLintPipeline, normalize_lint_run_mode
from knoarbor.runtime import configure_runtime_logging, runtime_logger
from knoarbor.runtime.run_monitor import list_runs, read_run, read_run_events, request_cancel
from knoarbor.runtime.endpoint import find_available_port, write_runtime_endpoint
from knoarbor.semantic import (
    IngestSemanticWorkflow,
    LintSemanticWorkflow,
    SemanticRunner,
    build_semantic_runner as build_configured_semantic_runner,
    load_semantic_contract,
)
from knoarbor.storage.page_namespace_migration import migrate_page_namespace
from knoarbor.storage.wiki_init import init_wiki_vault, migrate_wiki_pages_layout
from knoarbor.storage.wiki_paths import content_root
from knoarbor.cli_utils import (
    count_raw_sources,
    follow_run_events,
    print_doctor_details,
    print_json,
    print_run_metrics,
    read_json_object,
    resolve_config,
    resolve_config_path,
    resolve_vault_path,
)

def add_vault_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault", default=None, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    parser.add_argument("--vault-id", default=None, help="Configured vault profile ID. Ignored when --vault is provided.")


def run_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from knoarbor.entrypoints.api import create_app
    from knoarbor.services import ApplicationServices

    config = resolve_config(args)
    host = args.host or config.server.host
    preferred_port = args.port or config.server.port
    port, switched_port = find_available_port(host, preferred_port)
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    base_url = f"http://{display_host}:{port}"
    config_path = resolve_config_path(args)
    log_path = configure_runtime_logging(config.vault.path, console=True)
    endpoint_path = write_runtime_endpoint(
        config_path,
        host=display_host,
        port=port,
        base_url=base_url,
        vault_path=config.vault.path,
        vault_id=config.active_vault_id(),
        vault_name=config.active_vault_name(),
        vaults=config.vault_profiles_summary(),
    )
    if switched_port:
        _print_startup_line(f"Configured port {preferred_port} is in use; using {port} instead.")
    _print_startup_line(f"KnoArbor UI: {base_url}")
    _print_startup_line(f"UI alias: {base_url}/ui")
    _print_startup_line(f"API docs: {base_url}/docs")
    _print_startup_line(f"Runtime endpoint: {endpoint_path}")
    _print_startup_line(f"Runtime log: {log_path}")
    _print_serve_summary(config, config_path=config_path, base_url=base_url)
    runtime_logger("serve").info(
        "service_starting host=%s port=%s vault_id=%s vault_name=%s vault=%s config=%s ui=%s docs=%s model_provider=%s model=%s providers=%s connectors=%s log=%s endpoint=%s",
        host,
        port,
        config.active_vault_id(),
        config.active_vault_name(),
        config.vault.path,
        config_path,
        base_url,
        f"{base_url}/docs",
        config.models.default_provider or "-",
        _default_model_name(config),
        ",".join(sorted(config.models.providers.keys())) or "-",
        ",".join(config.enabled_connectors()) or "-",
        log_path,
        endpoint_path,
    )
    uvicorn.run(create_app(ApplicationServices()), host=host, port=port)
    return 0


def _print_serve_summary(config, *, config_path: Path, base_url: str) -> None:
    provider_name = config.models.default_provider
    provider = config.models.providers.get(provider_name) if provider_name else None
    _print_startup_line("Startup summary:")
    _print_startup_line(f"  Config: {config_path}")
    _print_startup_line(f"  Active vault: {config.active_vault_name()} ({config.active_vault_id()})")
    _print_startup_line(f"  Vault path: {config.vault.path}")
    _print_startup_line(f"  Vault profiles: {len(config.vaults.profiles)}")
    _print_startup_line(f"  Connectors: {', '.join(config.enabled_connectors()) or 'none'}")
    _print_startup_line(f"  Default model: {_provider_summary(provider_name, provider)}")
    _print_startup_line(f"  Health: {base_url}/health")


def _print_startup_line(message: str) -> None:
    print(message, flush=True)


def _provider_summary(provider_name: str | None, provider) -> str:
    if not provider_name or provider is None:
        return "not configured"
    auth = "no api key required" if not provider.api_key_env else f"api key env={provider.api_key_env}"
    base_url = provider.base_url or "default endpoint"
    model = provider.model or "model not set"
    return f"{provider_name} / {model} / {provider.adapter} / {base_url} / {auth}"


def _default_model_name(config) -> str:
    provider_name = config.models.default_provider
    provider = config.models.providers.get(provider_name) if provider_name else None
    return provider.model if provider and provider.model else "-"


def run_first_run(args: argparse.Namespace) -> int:
    config_path = resolve_bootstrap_config_path(args)
    config_created = ensure_local_config(config_path, vault_path=args.vault)
    config = resolve_config(args)
    vault_path = Path(args.vault).expanduser().resolve() if args.vault else config.vault.path
    init_result = init_wiki_vault(vault_path, force=False)
    example_path = install_first_run_example(vault_path) if args.with_example else None
    doctor_report = DoctorService().run(config_path=str(config_path))

    payload = {
        "config_path": str(config_path),
        "config_created": config_created,
        "vault": init_result.model_dump(),
        "example_path": str(example_path) if example_path else None,
        "doctor": doctor_report.model_dump(),
        "next_steps": _first_run_next_steps(example_installed=example_path is not None),
    }
    if args.json:
        print_json(payload)
        return 0 if doctor_report.status != "error" else 1

    print(f"config: {config_path} ({'created' if config_created else 'existing'})")
    print(f"vault: {init_result.vault_path}")
    print(f"created_paths: {len(init_result.created_paths)}")
    print(f"existing_paths: {len(init_result.existing_paths)}")
    if example_path:
        print(f"example: {example_path}")
    print(f"doctor: {doctor_report.status}")
    print(f"checks: {doctor_report.summary.get('ok', 0)} ok / {doctor_report.summary.get('warning', 0)} warning / {doctor_report.summary.get('error', 0)} error")
    print("\nNext steps:")
    for step in payload["next_steps"]:
        print(f"- {step}")
    return 0 if doctor_report.status != "error" else 1


def run_init(args: argparse.Namespace) -> int:
    config_path = resolve_bootstrap_config_path(args)
    config_created = ensure_local_config(config_path, vault_path=args.vault)
    config = resolve_config(args)
    vault_path = Path(args.vault).expanduser().resolve() if args.vault else config.vault.path
    result = init_wiki_vault(vault_path, force=args.force)
    if args.json:
        payload = result.model_dump()
        payload["config_path"] = str(config_path)
        payload["config_created"] = config_created
        print_json(payload)
        return 0

    print(f"config: {config_path} ({'created' if config_created else 'existing'})")
    print(f"vault: {result.vault_path}")
    print(f"created: {len(result.created_paths)}")
    print(f"existing: {len(result.existing_paths)}")
    for path in result.created_paths[:20]:
        print(f"- created {path}")
    return 0


def ensure_local_config(config_path: Path, *, vault_path: str | None = None) -> bool:
    """Create a local config from bundled defaults when first-run commands need one."""

    if config_path.exists():
        return False
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_bundled_example_config()
    if vault_path:
        project = dict(data.get("project") or {})
        vault_name = str(project.get("name") or "KnoArbor")
        vaults = dict(data.get("vaults") or {})
        profiles = dict(vaults.get("profiles") or {})
        default_id = str(vaults.get("default") or "default")
        profiles[default_id] = {"name": vault_name, "path": vault_path}
        data["vaults"] = {"default": default_id, "profiles": profiles}
        vault = dict(data.get("vault") or {})
        vault["path"] = vault_path
        data["vault"] = vault
    _write_yaml_config(config_path, data)
    return True


def resolve_bootstrap_config_path(args: argparse.Namespace) -> Path:
    if args.config:
        return Path(args.config).expanduser().resolve()
    return (Path.cwd() / "config.yaml").resolve()


def install_first_run_example(vault_path: Path) -> Path:
    target = vault_path / "raw" / "notes" / "agent-loop.md"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    text = files("knoarbor.examples").joinpath("agent-loop.md").read_text(encoding="utf-8")
    target.write_text(text, encoding="utf-8")
    return target


def _first_run_next_steps(*, example_installed: bool) -> list[str]:
    source_step = (
        "Run `uv run knoar ingest --connector markdown --write` to compile the bundled example or your Markdown notes."
        if example_installed
        else "Put Markdown notes under a configured markdown root, then run `uv run knoar ingest --connector markdown --write`."
    )
    steps = [
        "Set your model API key in .env if doctor reports models.api_key_env as error.",
        source_step,
    ]
    if example_installed:
        steps.append("Run `uv run knoar query \"Agent Loop 是什么？\"` after ingest completes.")
    steps.append("Start the local console with `uv run knoar serve`.")
    return steps


def _load_bundled_example_config() -> dict[str, object]:
    import yaml  # type: ignore[import-untyped]

    text = files("knoarbor").joinpath("config.example.yaml").read_text(encoding="utf-8")
    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Bundled config.example.yaml root must be an object")
    return loaded


def _write_yaml_config(path: Path, data: dict[str, object]) -> None:
    import yaml  # type: ignore[import-untyped]

    path.write_text(
        "# Local KnoArbor configuration. Secrets belong in .env, not in this file.\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def run_status(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    scan = WikiLintPipeline(privacy_config=config.privacy).scan(
        WikiScanRequest(
            vault_path=str(vault_path),
            max_chars_per_page=0,
        )
    )
    status = {
        "vault_path": str(vault_path),
        "content_root": str(content_root(vault_path)),
        "pages": len(scan.pages),
        "issues": len(scan.issues),
        "errors": scan.stats.get("error_count", 0),
        "warnings": scan.stats.get("warning_count", 0),
        "info": scan.stats.get("info_count", 0),
        "directories": scan.stats.get("directories", {}),
        "raw_sources": count_raw_sources(vault_path),
        "has_schema": (content_root(vault_path) / "SCHEMA.md").exists(),
        "has_index": (machine_index_dir(vault_path) / "manifest.json").exists() and (machine_index_dir(vault_path) / "graph_index.json").exists(),
        "has_log": (content_root(vault_path) / "log.md").exists(),
        "has_ignore": (vault_path / ".knoarborignore").exists(),
    }
    if args.json:
        print_json(status)
        return 0

    print(f"vault: {status['vault_path']}")
    print(f"content_root: {status['content_root']}")
    print(f"pages: {status['pages']}")
    print(f"raw_sources: {status['raw_sources']}")
    print(f"issues: {status['issues']} ({status['errors']} errors, {status['warnings']} warnings, {status['info']} info)")
    print(f"schema/index/log/ignore: {status['has_schema']}/{status['has_index']}/{status['has_log']}/{status['has_ignore']}")
    return 0


def run_vaults(args: argparse.Namespace) -> int:
    if getattr(args, "vaults_command", None) == "migrate-layout":
        config = resolve_config(args)
        vault_path = resolve_vault_path(args, config)
        result = migrate_wiki_pages_layout(vault_path)
        if args.json:
            print_json(result.model_dump())
            return 0
        print(f"vault: {result.vault_path}")
        print(f"content_root: {result.content_root}")
        print(f"moved: {len(result.moved_paths)}")
        print(f"skipped: {len(result.skipped_paths)}")
        for path in result.moved_paths:
            print(f"- moved {path}")
        return 0

    if getattr(args, "vaults_command", None) == "migrate-namespace":
        config = resolve_config(args)
        vault_path = resolve_vault_path(args, config)
        result = migrate_page_namespace(vault_path, dirs=args.dir, apply=args.apply)
        if args.json:
            print_json(result.model_dump())
            return 0 if result.can_apply or args.apply else 1
        print(f"vault: {result.vault_path}")
        print(f"content_root: {result.content_root}")
        print(f"mode: {'apply' if args.apply else 'dry-run'}")
        print(f"selected_dirs: {', '.join(result.selected_dirs) or '-'}")
        print(f"planned_moves: {len(result.planned_moves)}")
        print(f"moved: {len(result.moved_paths)}")
        print(f"link_rewrites: {sum(item.replacements for item in result.link_rewrites)}")
        print(f"conflicts: {len(result.conflicts)}")
        for conflict in result.conflicts[:20]:
            print(f"- conflict {conflict.source_path} -> {conflict.target_path}: {conflict.reason}")
        for move in (result.moved_paths if args.apply else result.planned_moves)[:40]:
            prefix = "moved" if args.apply else "plan"
            print(f"- {prefix} {move.source_path} -> {move.target_path} [{move.page_kind}]")
        if result.warnings:
            print("warnings:")
            for warning in result.warnings:
                print(f"- {warning}")
        return 0 if result.can_apply or args.apply else 1

    response = VaultRegistryService().list_vaults(config_path=args.config)
    if args.json:
        print_json(response.model_dump())
        return 0

    print(f"vaults: {len(response.vaults)}")
    print(f"default: {response.default_vault_id or '-'}")
    for vault in response.vaults:
        marker = "*" if vault.active else "-"
        status = "available" if vault.exists else "missing"
        print(f"{marker} {vault.id}  {vault.name}  {status}  {vault.path}")
    return 0


def run_doctor(args: argparse.Namespace) -> int:
    report = DoctorService().run(config_path=args.config, connector_names=args.connectors)
    if args.json:
        print_json(report.model_dump())
        return 0 if report.status != "error" else 1

    print(f"status: {report.status}")
    print(f"config: {report.config_path}")
    print(f"checks: {report.summary.get('ok', 0)} ok / {report.summary.get('warning', 0)} warning / {report.summary.get('error', 0)} error")
    for check in report.checks:
        print(f"- [{check.status}] {check.name}: {check.message}")
        print_doctor_details(check.details)
    if report.next_steps:
        print("\nNext steps:")
        for step in report.next_steps:
            print(f"- {step}")
    return 0 if report.status != "error" else 1


def run_runs(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    response = list_runs(vault_path, active_only=args.active, limit=args.limit)
    if args.json:
        print_json(response.model_dump())
        return 0
    if not response.runs:
        print("no runs")
        return 0
    for record in response.runs:
        current = f" · {record.current_item}" if record.current_item else ""
        print(f"{record.run_id}  {record.flow}  {record.status}  {record.stage}{current}  heartbeat={record.last_heartbeat_at}")
    return 0


def run_run_events(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    if args.follow and not args.json:
        return follow_run_events(vault_path, args.run_id, after=args.after)
    record = read_run(vault_path, args.run_id)
    events = read_run_events(vault_path, args.run_id, after=args.after)
    if args.json:
        print_json({"run": record.model_dump(), "events": [event.model_dump() for event in events]})
        return 0
    print(f"{record.run_id}  {record.flow}  {record.status}  {record.stage}")
    for event in events:
        print(f"[{event.sequence}] {event.created_at} {event.event_type} {event.stage} - {event.message}")
    return 0


def run_run_cancel(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    record = request_cancel(vault_path, args.run_id)
    if args.json:
        print_json(record.model_dump())
        return 0
    print(f"cancel_requested: {record.run_id} status={record.status}")
    return 0


def run_pages(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    config = select_config_vault(config, vault_path=str(vault_path), vault_id=args.vault_id)
    service = WikiPageService()
    vault_id = config.active_vault_id()
    vault_name = config.active_vault_name()

    if args.pages_command == "list":
        response = service.list_pages(vault_path, vault_id=vault_id, vault_name=vault_name)
        pages = response.pages
        if args.page_dir:
            pages = [page for page in pages if page.directory == args.page_dir]
        if args.contains:
            needle = args.contains.lower()
            pages = [page for page in pages if needle in f"{page.title} {page.path}".lower()]
        response = response.model_copy(update={"pages": pages})
        if args.json:
            print_json(response.model_dump())
            return 0
        print(f"pages: {len(response.pages)}")
        for page in response.pages[:80]:
            print(f"- {page.title} ({page.path}) [{page.directory}]")
        return 0

    if args.pages_command == "read":
        response = service.read_page(vault_path, args.path, vault_id=vault_id, vault_name=vault_name)
        if args.json:
            print_json(response.model_dump())
            return 0
        print(response.content)
        return 0

    if args.pages_command == "links":
        response = service.page_links(vault_path, args.path, vault_id=vault_id, vault_name=vault_name)
        if args.json:
            print_json(response.model_dump())
            return 0
        print(f"page: {response.path}")
        print("outbound_links:")
        for link in response.outbound_links:
            print(f"- {link.target_path or link.target} ({'resolved' if link.resolved else 'unresolved'})")
        print("backlinks:")
        for link in response.backlinks:
            print(f"- {link.source}")
        return 0

    return 2


def run_reports(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    config = select_config_vault(config, vault_path=str(vault_path), vault_id=args.vault_id)
    service = WikiReportService()
    vault_id = config.active_vault_id()
    vault_name = config.active_vault_name()

    if args.reports_command == "list":
        response = service.list_reports(vault_path, vault_id=vault_id, vault_name=vault_name)
        if args.json:
            print_json(response.model_dump())
            return 0
        print(f"reports: {len(response.reports)}")
        for report in response.reports[:80]:
            print(f"- {report.kind} {report.title} {report.updated} {report.path}")
        return 0

    if args.reports_command == "read":
        response = service.read_report(vault_path, args.path, vault_id=vault_id, vault_name=vault_name)
        if args.json:
            print_json(response.model_dump())
            return 0
        print(response.content)
        return 0

    return 2


def run_query(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    query_config = config.query
    response = WikiSearchService().search(
        WikiSearchRequest(
            vault_path=str(vault_path),
            query=args.query,
            mode=args.mode or query_config.mode,
            page_dirs=args.page_dirs if args.page_dirs is not None else query_config.page_dirs,
            max_results=args.max_results if args.max_results is not None else query_config.max_results,
            max_pages_to_read=args.max_pages_to_read if args.max_pages_to_read is not None else query_config.max_pages_to_read,
            max_excerpts_per_page=args.max_excerpts_per_page if args.max_excerpts_per_page is not None else query_config.max_excerpts_per_page,
            max_chars_per_excerpt=args.max_chars_per_excerpt if args.max_chars_per_excerpt is not None else query_config.max_chars_per_excerpt,
            max_context_chars=args.max_context_chars if args.max_context_chars is not None else query_config.max_context_chars,
            include_related=args.include_related if args.include_related is not None else query_config.include_related,
            record_query=args.record_query,
            write_report=args.write_report,
            caller="cli",
        )
    )
    if args.json:
        print_json(response.model_dump())
        return 0

    print(response.context_pack)
    if response.gaps:
        print("\nGaps:")
        for gap in response.gaps:
            print(f"- {gap}")
    if response.stats.get("query_report_path"):
        print(f"\nreport: {response.stats['query_report_path']}")
    return 0


def run_query_feedback(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    response = WikiSearchService().feedback(
        WikiQueryFeedbackRequest(
            vault_path=str(vault_path),
            query=args.query,
            useful=args.useful,
            selected_paths=args.selected_paths or [],
            rejected_paths=args.rejected_paths or [],
            comment=args.comment,
            caller="cli",
        )
    )
    if args.json:
        print_json(response.model_dump())
        return 0

    print(f"recorded: {response.recorded}")
    print(f"ledger: {response.ledger_path}")
    return 0


def run_scan(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    response = WikiLintPipeline(privacy_config=config.privacy).scan(
        WikiScanRequest(
            vault_path=str(vault_path),
            max_chars_per_page=args.max_chars_per_page,
        )
    )
    if args.json:
        print_json(response.model_dump())
        return 0

    print(f"pages: {len(response.pages)}")
    print(f"issues: {len(response.issues)}")
    print(f"fixes: {len(response.fixes)}")
    for issue in response.issues[:10]:
        print(f"- [{issue.severity}] {issue.code}: {issue.path} - {issue.message}")
    return 0


def run_lint(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    response = WikiLintPipeline(privacy_config=config.privacy).lint(
        WikiLintRequest(
            vault_path=str(vault_path),
            write_report=args.write_report,
            report_path=args.report_path,
            apply_safe_fixes=args.apply_safe_fixes,
        )
    )
    if args.json:
        print_json(response.model_dump())
        return 0

    print(f"issues: {len(response.issues)}")
    print(f"fixes: {len(response.fixes)}")
    if response.report_path:
        print(f"report: {response.report_path}")
    for issue in response.issues[:10]:
        print(f"- [{issue.severity}] {issue.code}: {issue.path} - {issue.message}")
    return 0


def run_lint_run(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    max_tokens = args.max_tokens or config.models.default_max_tokens
    max_candidates = args.max_candidates if args.max_candidates is not None else (16 if args.profile == "deep" else 8)
    max_chars_per_page = args.max_chars_per_page if args.max_chars_per_page is not None else (6000 if args.profile == "deep" else 2500)
    scope = MaintenanceScope(
        scope_id="manual:cli",
        trigger="manual",
        source=MaintenanceScopeSource(kind="cli"),
        changed_pages=args.scope_pages or [],
        recommended_lint_modes=[args.mode],
        reason="Manual lint maintenance run from CLI.",
    )
    internal_mode = normalize_lint_run_mode(args.mode)
    request = LintRunRequest(
        vault_path=str(vault_path),
        vault_id=args.vault_id,
        scope=scope,
        mode=internal_mode,
        profile=args.profile,
        apply_safe_fixes=args.apply_safe_fixes,
        include_related=args.include_related,
        max_candidates=max_candidates,
        max_chars_per_page=max_chars_per_page,
        max_tokens=max_tokens,
        auto_apply_reviewed_changes=args.apply_reviewed,
        write_report=args.write_report,
        append_ledger=args.append_ledger,
        provider=args.provider,
        config_path=args.config,
    )
    if _should_follow(args):
        started = RunManager().start_lint(request, WikiLinterService().run_maintenance)
        stream = sys.stderr if args.json else sys.stdout
        print(f"run_id: {started.run_id}", file=stream, flush=True)
        exit_code = follow_run_events(vault_path, started.run_id, stream=stream)
        if args.json:
            print_json(read_run(vault_path, started.run_id).model_dump())
        return exit_code

    response = WikiLinterService().run_maintenance(request)
    if args.json:
        print_json(response.model_dump())
        return 0

    lint = response.deterministic_lint
    policy = response.policy_decision
    print(f"mode: {response.mode}")
    print(f"profile: {response.profile}")
    print(f"scope_pages: {len(response.scope.changed_pages) or 'all'}")
    print(f"issues: {len(lint.issues)}")
    print(f"fixes: {len(lint.fixes)}")
    print(f"recommended_mode: {policy.recommended_mode}")
    print(f"policy_triggered: {policy.triggered}")
    if response.semantic_candidates:
        print(f"semantic_candidates: {len(response.semantic_candidates.get('candidates', []))}")
    if response.maintenance_review:
        print(f"reviewed: {len(response.maintenance_review.get('decisions', []))}")
    if response.applied_operations:
        print(f"applied_operations: {len(response.applied_operations)}")
    if response.written_pages:
        print(f"written_pages: {len(response.written_pages)}")
    print_run_metrics(response.metrics)
    if response.rescan:
        print(f"rescan_issues: {len(response.rescan.issues)}")
    if response.report_path:
        print(f"report: {response.report_path}")
    if response.ledger_path:
        print(f"ledger: {response.ledger_path}")
    for issue in lint.issues[:10]:
        print(f"- [{issue.severity}] {issue.code}: {issue.path} - {issue.message}")
    return 0


def run_sources(args: argparse.Namespace) -> int:
    if args.catalog:
        response = SourceCatalogService().list_catalog(
            config_path=args.config,
            connector_names=args.connectors,
        )
        if args.json:
            print_json(response.model_dump())
            return 0
        print(f"connectors: {len(response.connectors)}")
        for item in response.connectors:
            flags = []
            if item.enabled:
                flags.append("enabled")
            elif item.configured:
                flags.append("configured")
            if item.supports_checkpoint:
                flags.append("checkpoint")
            if item.supports_segmentation_hint:
                flags.append("segmentation")
            if item.requires_external_service:
                flags.append("external")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            source_types = ", ".join(item.source_types) or "none"
            print(f"- {item.name} ({item.version}) -> {source_types}{suffix}")
        return 0

    config = resolve_config(args)
    response = SourcePipeline().run_enabled(config, connector_names=args.connectors)
    if args.json:
        print_json(_source_preflight_payload(response.model_dump(), include_content=args.include_content))
        return 0

    print(f"connectors: {response.stats['connector_count']}")
    print(f"items: {response.stats['item_count']}")
    for result in response.results:
        print(f"- {result.connector}: {len(result.items)}")
        for item in result.items[:5]:
            print(f"  - {item.document.metadata.get('title') or item.ref.display_name} ({item.ref.source_type})")
    return 0


def _source_preflight_payload(payload: dict[str, object], *, include_content: bool) -> dict[str, object]:
    if include_content:
        return payload
    compact = dict(payload)
    compact_results: list[object] = []
    for result in _as_list(compact.get("results")):
        if not isinstance(result, dict):
            compact_results.append(result)
            continue
        compact_result = dict(result)
        compact_items: list[object] = []
        for item in _as_list(compact_result.get("items")):
            if not isinstance(item, dict):
                compact_items.append(item)
                continue
            compact_items.append(_compact_source_item(item))
        compact_result["items"] = compact_items
        compact_results.append(compact_result)
    compact["results"] = compact_results
    return compact


def _compact_source_item(item: dict[str, object]) -> dict[str, object]:
    compact = dict(item)
    document = compact.get("document")
    if not isinstance(document, dict):
        return compact
    compact_document = dict(document)
    content = compact_document.get("content")
    if isinstance(content, dict):
        text = content.get("text")
        sections = content.get("sections")
        compact_content = {
            "format": content.get("format"),
            "text_chars": len(text) if isinstance(text, str) else 0,
            "section_count": len(sections) if isinstance(sections, list) else 0,
        }
        compact_document["content"] = compact_content
    compact["document"] = compact_document
    return compact


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def run_ingest(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    config = select_config_vault(config, vault_path=str(vault_path), vault_id=args.vault_id)
    if getattr(args, "recover_run_id", None):
        return _run_ingest_recovery_from_args(args, config, args.recover_run_id)
    if getattr(args, "source_document", None):
        args.input = args.source_document
        return run_ingest_document(args)
    if getattr(args, "input", None):
        return run_ingest_path(args)
    if _should_follow(args):
        request = IngestRunRequest(
            config_path=args.config,
            vault_path=str(vault_path),
            vault_id=args.vault_id,
            connector_names=args.connectors,
            provider=args.provider,
            max_tokens=args.max_tokens or config.models.default_max_tokens,
            write=args.write,
            write_report=args.write_report,
            append_ledger=args.append_ledger,
            force_reprocess=args.force_reprocess,
        )
        started = RunManager().start_ingest(request, IngestService().run)
        stream = sys.stderr if args.json else sys.stdout
        print(f"run_id: {started.run_id}", file=stream, flush=True)
        exit_code = follow_run_events(vault_path, started.run_id, stream=stream)
        if args.json:
            print_json(read_run(vault_path, started.run_id).model_dump())
        return exit_code

    result = build_ingest_pipeline(args, config).run(
        config,
        connector_names=args.connectors,
        write=args.write,
        max_tokens=args.max_tokens or config.models.default_max_tokens,
        write_report=args.write_report,
        append_ledger=args.append_ledger,
        force_reprocess=args.force_reprocess,
    )
    if args.json:
        print_json(result.model_dump())
        return 0

    print(f"sources: {result.stats['source_count']}")
    print(f"processed: {result.stats['processed_count']}")
    print(f"skipped: {result.stats['skipped_count']}")
    print(f"failed: {result.stats.get('failed_count', 0)}")
    print(f"written: {result.stats['written_count']}")
    print_run_metrics(result.metrics)
    if result.report_path:
        print(f"report: {result.report_path}")
    if result.ledger_path:
        print(f"ledger: {result.ledger_path}")
    for item in result.results[:10]:
        status = item.status
        print(f"- [{status}] {item.connector}: {item.source_file} ({item.mode})")
        if item.status == "failed":
            print(f"  error: {item.error_stage} {item.error_type}: {item.error_message}")
        for page in item.generated_pages:
            print(f"  - {page}")
    return 0


def _run_ingest_recovery_from_args(args: argparse.Namespace, config, run_id: str) -> int:
    vault_path = resolve_vault_path(args, config)
    request = IngestRecoveryRunRequest(
        config_path=args.config,
        provider=args.provider,
        max_tokens=args.max_tokens,
        write=args.write,
        write_report=args.write_report,
        append_ledger=args.append_ledger,
        force_reprocess=args.force_reprocess,
    )
    started = RunManager().start_ingest_recovery(
        str(vault_path),
        run_id,
        request,
        IngestService().run,
        IngestService().run_file,
        IngestService().run_folder,
    )
    stream = sys.stderr if args.json else sys.stdout
    print(f"run_id: {started.run_id}", file=stream, flush=True)
    exit_code = follow_run_events(vault_path, started.run_id, stream=stream) if _should_follow(args) else 0
    if args.json:
        print_json(read_run(vault_path, started.run_id).model_dump())
    return exit_code


def run_ingest_document(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    document = SourceDocument.model_validate(read_json_object(args.input))
    result = build_ingest_pipeline(args, config).run_document(
        document,
        vault_path=vault_path,
        write=args.write,
        max_tokens=args.max_tokens or config.models.default_max_tokens,
        privacy_config=config.privacy,
        write_report=args.write_report,
        append_ledger=args.append_ledger,
        auto_scoped_lint=config.ingest.auto_scoped_lint,
        auto_apply_safe_lint_fixes=config.ingest.auto_apply_safe_lint_fixes,
        scoped_lint_include_related=config.lint.scoped_include_related,
    )
    response: dict[str, object] = {"result": result.model_dump()}

    if args.json:
        print_json(response)
        return 0

    semantic_result = result.semantic_result
    print(f"operations: {len(semantic_result.wiki_page_plan.operations) if semantic_result else 0}")
    print(f"drafts: {len(semantic_result.wiki_draft_batch.drafts) if semantic_result else 0}")
    print(f"approved: {len(result.approved_operation_indexes)}")
    if result.status == "failed":
        print(f"failed: {result.error_stage} {result.error_type}: {result.error_message}")
    print(f"written: {len(result.generated_pages)}" if args.write else "write: disabled")
    print_run_metrics(result.metrics)
    if result.report_path:
        print(f"report: {result.report_path}")
    if result.ledger_path:
        print(f"ledger: {result.ledger_path}")
    return 0


def run_ingest_path(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser()
    if input_path.is_dir():
        return run_ingest_folder(args)
    return run_ingest_file(args)


def run_ingest_file(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    request = IngestFileRunRequest(
        input_path=args.input,
        config_path=args.config,
        vault_path=str(vault_path),
        vault_id=args.vault_id,
        provider=args.provider,
        max_tokens=args.max_tokens or config.models.default_max_tokens,
        write=args.write,
        write_report=args.write_report,
        append_ledger=args.append_ledger,
        force_reprocess=args.force_reprocess,
    )
    if _should_follow(args):
        started = RunManager().start_ingest_file(request, IngestService().run_file)
        stream = sys.stderr if args.json else sys.stdout
        print(f"run_id: {started.run_id}", file=stream, flush=True)
        exit_code = follow_run_events(vault_path, started.run_id, stream=stream)
        if args.json:
            print_json(read_run(vault_path, started.run_id).model_dump())
        return exit_code

    result = IngestService().run_file(
        request
    )

    if args.json:
        print_json(result.model_dump())
        return 0

    print(f"sources: {result.stats['source_count']}")
    print(f"processed: {result.stats['processed_count']}")
    print(f"skipped: {result.stats['skipped_count']}")
    print(f"failed: {result.stats.get('failed_count', 0)}")
    print(f"written: {result.stats['written_count']}")
    if result.document_processing.items:
        item = result.document_processing.items[0]
        print(f"preprocessed: {item.input_path} -> {item.output_path}")
    print_run_metrics(result.metrics)
    if result.report_path:
        print(f"report: {result.report_path}")
    if result.ledger_path:
        print(f"ledger: {result.ledger_path}")
    for item in result.results[:10]:
        print(f"- [{item.status}] {item.connector}: {item.source_file} ({item.mode})")
        for page in item.generated_pages:
            print(f"  - {page}")
    return 0


def run_ingest_folder(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    request = IngestFolderRunRequest(
        input_path=args.input,
        connector_names=args.connectors,
        config_path=args.config,
        vault_path=str(vault_path),
        vault_id=args.vault_id,
        provider=args.provider,
        max_tokens=args.max_tokens or config.models.default_max_tokens,
        write=args.write,
        write_report=args.write_report,
        append_ledger=args.append_ledger,
        force_reprocess=args.force_reprocess,
    )
    if _should_follow(args):
        started = RunManager().start_ingest_folder(request, IngestService().run_folder)
        stream = sys.stderr if args.json else sys.stdout
        print(f"run_id: {started.run_id}", file=stream, flush=True)
        exit_code = follow_run_events(vault_path, started.run_id, stream=stream)
        if args.json:
            print_json(read_run(vault_path, started.run_id).model_dump())
        return exit_code

    result = IngestService().run_folder(request)

    if args.json:
        print_json(result.model_dump())
        return 0

    print(f"sources: {result.stats['source_count']}")
    print(f"processed: {result.stats['processed_count']}")
    print(f"skipped: {result.stats['skipped_count']}")
    print(f"failed: {result.stats.get('failed_count', 0)}")
    print(f"written: {result.stats['written_count']}")
    if result.document_processing.items:
        print(f"preprocessed: {result.document_processing.stats.get('processed_count', 0)}")
    print_run_metrics(result.metrics)
    if result.report_path:
        print(f"report: {result.report_path}")
    if result.ledger_path:
        print(f"ledger: {result.ledger_path}")
    for item in result.results[:10]:
        print(f"- [{item.status}] {item.connector}: {item.source_file} ({item.mode})")
        for page in item.generated_pages:
            print(f"  - {page}")
    return 0


def _should_follow(args: argparse.Namespace) -> bool:
    if args.follow is not None:
        return bool(args.follow)
    return not bool(getattr(args, "json", False))


def build_ingest_pipeline(args: argparse.Namespace, config) -> IngestPipeline:
    return IngestPipeline(
        IngestSemanticWorkflow(build_semantic_runner(args, config)),
        semantic_workflow_factory=lambda: IngestSemanticWorkflow(build_semantic_runner(args, config)),
        context_provider=IngestContextProvider(
            candidate_limit=config.ingest.candidate_limit,
            materialized_page_limit=config.ingest.materialized_page_limit,
            max_chars_per_page=config.ingest.max_chars_per_materialized_page,
        ),
    )


def run_lint_plan(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    vault_path = resolve_vault_path(args, config)
    pipeline = WikiLintPipeline(privacy_config=config.privacy)
    semantic = LintSemanticWorkflow(build_semantic_runner(args, config))

    if args.mode == "structural":
        scan = pipeline.scan(
            WikiScanRequest(
                vault_path=str(vault_path),
                max_chars_per_page=args.max_chars_per_page,
            )
        )
        source_payload: dict[str, object] = {"scan": scan.model_dump()}
        if not scan.issues:
            response = {
                "mode": args.mode,
                "source": {
                    "scan": {
                        "issues": [],
                        "fixes": [],
                        "stats": scan.stats,
                    }
                },
                "maintenance_candidates": {
                    "schema_version": "maintenance_candidates.v1",
                    "candidates": [],
                    "page_reviews": [],
                    "summary": "No structural lint issues found.",
                    "warnings": [],
                },
                "maintenance_review": {
                    "schema_version": "lint_maintenance_review.v1",
                    "decisions": [],
                    "summary": "No structural lint changes to review.",
                    "warnings": [],
                },
            }
            if args.json:
                print_json(response)
                return 0
            print("No structural lint issues found.")
            return 0
        candidates = semantic.diagnose_structural({"scan": scan.model_dump()}, max_tokens=args.max_tokens or config.models.default_max_tokens)
    else:
        selected = pipeline.select_candidates(
            WikiLintCandidateSelectRequest(
                vault_path=str(vault_path),
                mode="quality",
                max_candidates=args.max_candidates,
                max_chars_per_page=args.max_chars_per_page,
            )
        )
        candidates = semantic.diagnose_quality({"selected_pages": selected.model_dump()}, max_tokens=args.max_tokens or config.models.default_max_tokens)
        source_payload = {"selected_pages": selected.model_dump()}

    review = semantic.review(
        {
            "maintenance_candidates": candidates.model_dump(),
            "items": [candidate.model_dump() for candidate in candidates.candidates],
        },
        max_tokens=args.max_tokens or config.models.default_max_tokens,
    )
    response = {
        "mode": args.mode,
        "source": source_payload,
        "maintenance_candidates": candidates.model_dump(),
        "maintenance_review": review.model_dump(),
    }
    if args.json:
        print_json(response)
        return 0

    approved_count = sum(1 for decision in review.decisions if decision.decision == "approve")
    print(f"candidates: {len(candidates.candidates)}")
    print(f"reviewed: {len(review.decisions)}")
    print(f"approved: {approved_count}")
    print(review.summary)
    return 0


def run_contracts(args: argparse.Namespace) -> int:
    names = [
        "source_normalize",
        "wiki_page_plan",
        "wiki_draft_compile",
        "ingest_draft_review",
        "lint_diagnose",
        "lint_quality_diagnose",
        "lint_maintenance_review",
        "lint_draft_compile",
    ]
    rows = []
    for name in names:
        contract = load_semantic_contract(name)
        rows.append(
            {
                "name": contract.name,
                "schema_version": contract.schema_version,
                "schema_model": contract.schema_model.__name__,
                "prompt_name": contract.prompt_name,
            }
        )
    if args.json:
        print_json(rows)
        return 0
    for row in rows:
        print(f"- {row['name']}: {row['schema_version']} ({row['prompt_name']})")
    return 0


def run_contract(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    payload = read_json_object(args.input)
    result = build_semantic_runner(args, config).run(
        args.contract,
        payload,
        temperature=args.temperature,
        max_tokens=args.max_tokens or config.models.default_max_tokens,
    )
    print_json(
        {
            "contract_name": result.contract_name,
            "schema_version": result.schema_version,
            "provider": result.provider,
            "model": result.model,
            "output": result.output.model_dump(),
        }
    )
    return 0


def build_semantic_runner(args: argparse.Namespace, config) -> SemanticRunner:
    return build_configured_semantic_runner(config, getattr(args, "provider", None))
