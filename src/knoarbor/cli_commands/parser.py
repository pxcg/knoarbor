from __future__ import annotations

import argparse

from knoarbor.cli_commands.handlers import (
    add_vault_argument,
    run_contract,
    run_contracts,
    run_desktop_config,
    run_doctor,
    run_first_run,
    run_ingest,
    run_init,
    run_lint_plan,
    run_lint_run,
    run_pages,
    run_query,
    run_query_feedback,
    run_reports,
    run_run_cancel,
    run_run_events,
    run_runs,
    run_scan,
    run_serve,
    run_sources,
    run_status,
    run_vaults,
)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KnoArbor local command line interface.")
    parser.add_argument("--config", default=None, help="Path to config.yaml. Defaults to ./config.yaml or config.example.yaml.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    first_run_parser = subparsers.add_parser("first-run", help="Create local config, initialize the vault, and run first-run diagnostics.")
    first_run_parser.add_argument("--vault", default=None, help="Vault path to create. Defaults to ./vaults/default in the local config.")
    first_run_parser.add_argument(
        "--example",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="with_example",
        help="Copy a small bundled Markdown example into the vault raw notes directory. Enabled by default.",
    )
    first_run_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    first_run_parser.set_defaults(handler=run_first_run)

    serve_parser = subparsers.add_parser("serve", help="Start the local FastAPI service.")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.set_defaults(handler=run_serve)

    init_parser = subparsers.add_parser("init", help="Initialize a local KnoArbor vault.")
    init_parser.add_argument("--vault", default=None, help="Vault path to create. Defaults to config.yaml vault.path.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite .knoarborignore if it already exists.")
    init_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    init_parser.set_defaults(handler=run_init)

    status_parser = subparsers.add_parser("status", help="Print a local wiki health summary.")
    add_vault_argument(status_parser)
    status_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    status_parser.set_defaults(handler=run_status)

    vaults_parser = subparsers.add_parser("vaults", help="List configured KnoArbor knowledge bases.")
    vaults_subparsers = vaults_parser.add_subparsers(dest="vaults_command")
    vaults_list_parser = vaults_subparsers.add_parser("list", help="List configured vault profiles.")
    vaults_list_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    vaults_list_parser.set_defaults(handler=run_vaults)
    vaults_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    vaults_parser.set_defaults(handler=run_vaults)

    doctor_parser = subparsers.add_parser("doctor", help="Check local setup readiness without running semantic workflows.")
    doctor_parser.add_argument(
        "--connector",
        action="append",
        dest="connectors",
        default=None,
        help="Connector name to diagnose. Can be repeated. Defaults to enabled connectors in config.yaml.",
    )
    doctor_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    doctor_parser.set_defaults(handler=run_doctor)

    runs_parser = subparsers.add_parser("runs", help="List recent or active workflow runs.")
    add_vault_argument(runs_parser)
    runs_parser.add_argument("--active", action="store_true", help="Show only active runs.")
    runs_parser.add_argument("--limit", type=int, default=20)
    runs_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    runs_parser.set_defaults(handler=run_runs)

    runs_subparsers = runs_parser.add_subparsers(dest="runs_command")

    runs_list_parser = runs_subparsers.add_parser("list", help="List recent or active workflow runs.")
    runs_list_parser.add_argument("--vault", default=argparse.SUPPRESS, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    runs_list_parser.add_argument("--active", action="store_true", default=argparse.SUPPRESS, help="Show only active runs.")
    runs_list_parser.add_argument("--limit", type=int, default=argparse.SUPPRESS)
    runs_list_parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Print the full JSON response.")
    runs_list_parser.set_defaults(handler=run_runs)

    run_events_parser = runs_subparsers.add_parser("events", help="Show event log for one workflow run.")
    run_events_parser.add_argument("--vault", default=argparse.SUPPRESS, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    run_events_parser.add_argument("run_id")
    run_events_parser.add_argument("--after", type=int, default=0)
    run_events_parser.add_argument("--follow", action="store_true", help="Poll events until the run reaches a terminal state.")
    run_events_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    run_events_parser.set_defaults(handler=run_run_events)

    run_cancel_parser = runs_subparsers.add_parser("cancel", help="Request cooperative cancellation for one active run.")
    run_cancel_parser.add_argument("--vault", default=argparse.SUPPRESS, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    run_cancel_parser.add_argument("run_id")
    run_cancel_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    run_cancel_parser.set_defaults(handler=run_run_cancel)

    pages_parser = subparsers.add_parser("pages", help="List, read, or inspect generated wiki pages.")
    add_vault_argument(pages_parser)
    pages_subparsers = pages_parser.add_subparsers(dest="pages_command", required=True)
    pages_list_parser = pages_subparsers.add_parser("list", help="List wiki pages.")
    pages_list_parser.add_argument("--vault", default=argparse.SUPPRESS, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    pages_list_parser.add_argument("--vault-id", default=argparse.SUPPRESS, help="Configured vault profile ID. Ignored when --vault is provided.")
    pages_list_parser.add_argument("--dir", dest="page_dir", default=None, help="Limit to one physical page area such as pages or sources.")
    pages_list_parser.add_argument("--contains", default=None, help="Filter by title or path substring.")
    pages_list_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    pages_list_parser.set_defaults(handler=run_pages)
    pages_read_parser = pages_subparsers.add_parser("read", help="Read one wiki page by path.")
    pages_read_parser.add_argument("--vault", default=argparse.SUPPRESS, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    pages_read_parser.add_argument("--vault-id", default=argparse.SUPPRESS, help="Configured vault profile ID. Ignored when --vault is provided.")
    pages_read_parser.add_argument("path")
    pages_read_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    pages_read_parser.set_defaults(handler=run_pages)
    pages_relations_parser = pages_subparsers.add_parser("relations", help="Read page relations for one wiki page.")
    pages_relations_parser.add_argument("--vault", default=argparse.SUPPRESS, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    pages_relations_parser.add_argument("--vault-id", default=argparse.SUPPRESS, help="Configured vault profile ID. Ignored when --vault is provided.")
    pages_relations_parser.add_argument("path")
    pages_relations_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    pages_relations_parser.set_defaults(handler=run_pages)

    reports_parser = subparsers.add_parser("reports", help="List or read workflow reports.")
    add_vault_argument(reports_parser)
    reports_subparsers = reports_parser.add_subparsers(dest="reports_command", required=True)
    reports_list_parser = reports_subparsers.add_parser("list", help="List reports from the selected vault.")
    reports_list_parser.add_argument("--vault", default=argparse.SUPPRESS, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    reports_list_parser.add_argument("--vault-id", default=argparse.SUPPRESS, help="Configured vault profile ID. Ignored when --vault is provided.")
    reports_list_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    reports_list_parser.set_defaults(handler=run_reports)
    reports_read_parser = reports_subparsers.add_parser("read", help="Read one report by maintenance path.")
    reports_read_parser.add_argument("--vault", default=argparse.SUPPRESS, help="Path to the Obsidian wiki vault. Overrides config.yaml.")
    reports_read_parser.add_argument("--vault-id", default=argparse.SUPPRESS, help="Configured vault profile ID. Ignored when --vault is provided.")
    reports_read_parser.add_argument("path")
    reports_read_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    reports_read_parser.set_defaults(handler=run_reports)

    query_parser = subparsers.add_parser("query", help="Retrieve relevant wiki context for a question.")
    add_vault_argument(query_parser)
    query_parser.add_argument("query", help="Search query.")
    query_parser.add_argument("--mode", choices=["quick", "balanced", "deep"], default=None)
    query_parser.add_argument("--page-dir", action="append", dest="page_dirs", default=None, help="Limit search to one wiki directory. Can be repeated.")
    query_parser.add_argument("--max-results", type=int, default=None)
    query_parser.add_argument("--max-pages-to-read", type=int, default=None)
    query_parser.add_argument("--max-excerpts-per-page", type=int, default=None)
    query_parser.add_argument("--max-chars-per-excerpt", type=int, default=None)
    query_parser.add_argument("--max-context-chars", type=int, default=None)
    query_parser.add_argument("--include-related", action=argparse.BooleanOptionalAction, default=None)
    query_parser.add_argument("--record-query", action=argparse.BooleanOptionalAction, default=True)
    query_parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=False)
    query_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    query_parser.set_defaults(handler=run_query)

    query_feedback_parser = subparsers.add_parser("query-feedback", help="Record relevance feedback for a previous query.")
    add_vault_argument(query_feedback_parser)
    query_feedback_parser.add_argument("query", help="Original query.")
    query_feedback_parser.add_argument("--useful", action=argparse.BooleanOptionalAction, default=None)
    query_feedback_parser.add_argument("--selected-path", action="append", dest="selected_paths", default=None)
    query_feedback_parser.add_argument("--rejected-path", action="append", dest="rejected_paths", default=None)
    query_feedback_parser.add_argument("--comment", default="")
    query_feedback_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    query_feedback_parser.set_defaults(handler=run_query_feedback)

    scan_parser = subparsers.add_parser("scan", help="Diagnostic: run deterministic wiki scan without writing a report.")
    add_vault_argument(scan_parser)
    scan_parser.add_argument("--max-chars-per-page", type=int, default=2500)
    scan_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    scan_parser.set_defaults(handler=run_scan)

    lint_parser = subparsers.add_parser("lint", help="Run the unified lint maintenance workflow.")
    add_vault_argument(lint_parser)
    _add_lint_run_arguments(lint_parser)
    lint_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    lint_parser.set_defaults(handler=run_lint_run)

    sources_parser = subparsers.add_parser("sources", help="Normalize source documents from enabled connectors.")
    sources_parser.add_argument(
        "--connector",
        action="append",
        dest="connectors",
        default=None,
        help="Connector name to run. Can be repeated. Defaults to all enabled connectors in config.yaml.",
    )
    sources_parser.add_argument("--json", action="store_true", help="Print compact source preflight JSON.")
    sources_parser.add_argument(
        "--catalog",
        action="store_true",
        help="Print connector capability catalog instead of reading source documents.",
    )
    sources_parser.add_argument(
        "--include-content",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include full normalized source document content in JSON output.",
    )
    sources_parser.set_defaults(handler=run_sources)

    desktop_config_parser = subparsers.add_parser(
        "desktop-config",
        help="Desktop IPC helper: read or write local configuration as JSON without HTTP.",
    )
    desktop_config_parser.add_argument(
        "action",
        choices=["read-raw", "write-raw", "read-form", "write-form", "diagnostics", "vaults"],
        help="Config operation to run.",
    )
    desktop_config_parser.add_argument("--input", default="-", help="JSON payload file. Defaults to stdin.")
    desktop_config_parser.add_argument("--refresh-source-counts", action="store_true", help="Refresh source count diagnostics.")
    desktop_config_parser.add_argument("--json", action="store_true", help="Print the JSON response.")
    desktop_config_parser.set_defaults(handler=run_desktop_config)

    ingest_parser = subparsers.add_parser("ingest", help="Run the unified ingest workflow.")
    add_vault_argument(ingest_parser)
    ingest_parser.add_argument(
        "--connector",
        action="append",
        dest="connectors",
        default=None,
        help="Connector name to ingest. Can be repeated. Defaults to all enabled connectors in config.yaml.",
    )
    ingest_parser.add_argument(
        "--input",
        default=None,
        help="Optional file or folder path. Markdown runs directly; non-Markdown requires configured preprocessing.",
    )
    ingest_parser.add_argument(
        "--source-document",
        default=None,
        help="Optional prepared source_document.v1 JSON file.",
    )
    ingest_parser.add_argument(
        "--recover-run-id",
        default=None,
        help="Start a recovery ingest run from a failed or partially failed ingest run.",
    )
    ingest_parser.add_argument("--provider", default=None, help="Model provider name. Defaults to models.default_provider.")
    ingest_parser.add_argument("--max-tokens", type=int, default=None)
    ingest_parser.add_argument("--write", action=argparse.BooleanOptionalAction, default=False)
    ingest_parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    ingest_parser.add_argument("--append-ledger", action=argparse.BooleanOptionalAction, default=True)
    ingest_parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Ignore source checkpoints for this ingest run without deleting checkpoint state.",
    )
    ingest_parser.add_argument(
        "--follow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run through the local queue and print progress events. Defaults to on unless --json is used.",
    )
    ingest_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    ingest_parser.set_defaults(handler=run_ingest)

    _add_dev_commands(subparsers)

    return parser


def _add_lint_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=["deterministic", "semantic"], default="deterministic")
    parser.add_argument("--scope-page", action="append", dest="scope_pages", default=None, help="Page path to include in maintenance scope. Can be repeated. Defaults to full vault.")
    parser.add_argument("--provider", default=None, help="Model provider name for semantic modes. Defaults to models.default_provider.")
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--max-chars-per-page", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--include-related", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--apply-safe-fixes", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--apply-reviewed", action=argparse.BooleanOptionalAction, default=True, help="Apply approved semantic maintenance operations and rescan.")
    parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--append-ledger", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--follow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run through the local queue and print progress events. Defaults to on unless --json is used.",
    )


def _add_dev_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register developer diagnostics separately from product workflow commands."""

    lint_plan_parser = subparsers.add_parser(
        "lint-plan",
        help="Developer diagnostic: run semantic lint diagnosis and review without writing changes.",
    )
    add_vault_argument(lint_plan_parser)
    lint_plan_parser.add_argument("--provider", default=None, help="Model provider name. Defaults to models.default_provider.")
    lint_plan_parser.add_argument("--mode", choices=["deterministic", "semantic"], default="semantic")
    lint_plan_parser.add_argument("--max-candidates", type=int, default=8)
    lint_plan_parser.add_argument("--max-chars-per-page", type=int, default=2500)
    lint_plan_parser.add_argument("--max-tokens", type=int, default=None)
    lint_plan_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    lint_plan_parser.set_defaults(handler=run_lint_plan)

    contracts_parser = subparsers.add_parser(
        "contracts",
        help="Developer diagnostic: list known semantic contracts.",
    )
    contracts_parser.add_argument("--json", action="store_true", help="Print contracts as JSON.")
    contracts_parser.set_defaults(handler=run_contracts)

    run_contract_parser = subparsers.add_parser(
        "run-contract",
        help="Developer diagnostic: run one semantic contract with the configured model.",
    )
    run_contract_parser.add_argument("contract", help="Semantic contract name, such as source_normalize or lint_diagnose.")
    run_contract_parser.add_argument("--input", required=True, help="Path to a JSON input payload.")
    run_contract_parser.add_argument("--provider", default=None, help="Model provider name. Defaults to models.default_provider.")
    run_contract_parser.add_argument("--temperature", type=float, default=0.1)
    run_contract_parser.add_argument("--max-tokens", type=int, default=None)
    run_contract_parser.set_defaults(handler=run_contract)
