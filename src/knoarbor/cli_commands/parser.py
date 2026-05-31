from __future__ import annotations

import argparse

from knoarbor.cli_commands.handlers import (
    add_vault_argument,
    run_contract,
    run_contracts,
    run_doctor,
    run_ingest,
    run_ingest_document,
    run_ingest_file,
    run_init,
    run_lint,
    run_lint_plan,
    run_lint_run,
    run_query,
    run_query_feedback,
    run_run_cancel,
    run_run_events,
    run_run_rerun_failed,
    run_runs,
    run_scan,
    run_serve,
    run_sources,
    run_status,
)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KnoArbor local command line interface.")
    parser.add_argument("--config", default=None, help="Path to config.yaml. Defaults to ./config.yaml or config.example.yaml.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the local FastAPI service.")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.set_defaults(handler=run_serve)

    init_parser = subparsers.add_parser("init", help="Initialize a local KnoArbor vault.")
    init_parser.add_argument("--vault", default=None, help="Vault path to create. Defaults to config.yaml vault.path.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite SCHEMA.md and .knoarborignore if they already exist.")
    init_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    init_parser.set_defaults(handler=run_init)

    status_parser = subparsers.add_parser("status", help="Print a local wiki health summary.")
    add_vault_argument(status_parser)
    status_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    status_parser.set_defaults(handler=run_status)

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

    run_events_parser = subparsers.add_parser("run-events", help="Show event log for one workflow run.")
    add_vault_argument(run_events_parser)
    run_events_parser.add_argument("run_id")
    run_events_parser.add_argument("--after", type=int, default=0)
    run_events_parser.add_argument("--follow", action="store_true", help="Poll events until the run reaches a terminal state.")
    run_events_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    run_events_parser.set_defaults(handler=run_run_events)

    run_cancel_parser = subparsers.add_parser("run-cancel", help="Request cooperative cancellation for one active run.")
    add_vault_argument(run_cancel_parser)
    run_cancel_parser.add_argument("run_id")
    run_cancel_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    run_cancel_parser.set_defaults(handler=run_run_cancel)

    run_rerun_parser = subparsers.add_parser("run-rerun-failed", help="Start a recovery ingest run from a failed or partially failed ingest run.")
    add_vault_argument(run_rerun_parser)
    run_rerun_parser.add_argument("run_id")
    run_rerun_parser.add_argument("--provider", default=None, help="Override the model provider for the recovery run.")
    run_rerun_parser.add_argument("--max-tokens", type=int, default=None)
    run_rerun_parser.add_argument("--write", action=argparse.BooleanOptionalAction, default=None)
    run_rerun_parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=None)
    run_rerun_parser.add_argument("--append-ledger", action=argparse.BooleanOptionalAction, default=None)
    run_rerun_parser.add_argument(
        "--follow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Print progress events for the recovery run. Defaults to on unless --json is used.",
    )
    run_rerun_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    run_rerun_parser.set_defaults(handler=run_run_rerun_failed)

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
    query_parser.add_argument("--context-format", choices=["compact", "full"], default=None)
    query_parser.add_argument("--include-related", action=argparse.BooleanOptionalAction, default=None)
    query_parser.add_argument("--include-content", action=argparse.BooleanOptionalAction, default=None)
    query_parser.add_argument("--max-chars-per-page", type=int, default=None)
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

    lint_parser = subparsers.add_parser("lint", help="Diagnostic: run deterministic wiki lint and optionally write a report.")
    add_vault_argument(lint_parser)
    lint_parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    lint_parser.add_argument("--report-path", default=None)
    lint_parser.add_argument("--apply-safe-fixes", action="store_true")
    lint_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    lint_parser.set_defaults(handler=run_lint)

    lint_run_parser = subparsers.add_parser("lint-run", help="Run the primary unified lint maintenance contract.")
    add_vault_argument(lint_run_parser)
    lint_run_parser.add_argument("--mode", choices=["structural", "quality", "full"], default="structural")
    lint_run_parser.add_argument("--profile", choices=["standard", "deep"], default="standard")
    lint_run_parser.add_argument("--scope-page", action="append", dest="scope_pages", default=None, help="Page path to include in maintenance scope. Can be repeated. Defaults to full vault.")
    lint_run_parser.add_argument("--provider", default=None, help="Model provider name for semantic modes. Defaults to models.default_provider.")
    lint_run_parser.add_argument("--max-candidates", type=int, default=None)
    lint_run_parser.add_argument("--max-chars-per-page", type=int, default=None)
    lint_run_parser.add_argument("--max-tokens", type=int, default=None)
    lint_run_parser.add_argument("--include-related", action=argparse.BooleanOptionalAction, default=True)
    lint_run_parser.add_argument("--apply-safe-fixes", action=argparse.BooleanOptionalAction, default=True)
    lint_run_parser.add_argument("--apply-reviewed", action="store_true", help="Apply approved semantic maintenance operations and rescan.")
    lint_run_parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    lint_run_parser.add_argument("--append-ledger", action=argparse.BooleanOptionalAction, default=True)
    lint_run_parser.add_argument(
        "--follow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run through the local queue and print progress events. Defaults to on unless --json is used.",
    )
    lint_run_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    lint_run_parser.set_defaults(handler=run_lint_run)

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
        "--include-content",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include full normalized source document content in JSON output.",
    )
    sources_parser.set_defaults(handler=run_sources)

    ingest_parser = subparsers.add_parser("ingest", help="Run the local connector-based ingest workflow.")
    ingest_parser.add_argument(
        "--connector",
        action="append",
        dest="connectors",
        default=None,
        help="Connector name to ingest. Can be repeated. Defaults to all enabled connectors in config.yaml.",
    )
    ingest_parser.add_argument("--provider", default=None, help="Model provider name. Defaults to models.default_provider.")
    ingest_parser.add_argument("--max-tokens", type=int, default=None)
    ingest_parser.add_argument("--write", action=argparse.BooleanOptionalAction, default=False)
    ingest_parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    ingest_parser.add_argument("--append-ledger", action=argparse.BooleanOptionalAction, default=True)
    ingest_parser.add_argument(
        "--follow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run through the local queue and print progress events. Defaults to on unless --json is used.",
    )
    ingest_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    ingest_parser.set_defaults(handler=run_ingest)

    ingest_document_parser = subparsers.add_parser(
        "ingest-document",
        help="Run the local semantic ingest chain for one source_document.v1 JSON file.",
    )
    add_vault_argument(ingest_document_parser)
    ingest_document_parser.add_argument("--input", required=True, help="Path to a source_document.v1 JSON file.")
    ingest_document_parser.add_argument("--provider", default=None, help="Model provider name. Defaults to models.default_provider.")
    ingest_document_parser.add_argument("--max-tokens", type=int, default=None)
    ingest_document_parser.add_argument("--write", action=argparse.BooleanOptionalAction, default=False)
    ingest_document_parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    ingest_document_parser.add_argument("--append-ledger", action=argparse.BooleanOptionalAction, default=True)
    ingest_document_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    ingest_document_parser.set_defaults(handler=run_ingest_document)

    ingest_file_parser = subparsers.add_parser(
        "ingest-file",
        help="Ingest one file path. Markdown files run directly; non-Markdown files require configured MinerU preprocessing.",
    )
    ingest_file_parser.add_argument("--input", required=True, help="Path to a Markdown or rich document file.")
    ingest_file_parser.add_argument("--provider", default=None, help="Model provider name. Defaults to models.default_provider.")
    ingest_file_parser.add_argument("--max-tokens", type=int, default=None)
    ingest_file_parser.add_argument("--write", action=argparse.BooleanOptionalAction, default=False)
    ingest_file_parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    ingest_file_parser.add_argument("--append-ledger", action=argparse.BooleanOptionalAction, default=True)
    ingest_file_parser.add_argument(
        "--follow",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run through the local queue and print progress events. Defaults to on unless --json is used.",
    )
    ingest_file_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    ingest_file_parser.set_defaults(handler=run_ingest_file)

    lint_plan_parser = subparsers.add_parser(
        "lint-plan",
        help="Diagnostic: run local semantic lint diagnosis and review without writing changes.",
    )
    add_vault_argument(lint_plan_parser)
    lint_plan_parser.add_argument("--provider", default=None, help="Model provider name. Defaults to models.default_provider.")
    lint_plan_parser.add_argument("--mode", choices=["structural", "quality"], default="structural")
    lint_plan_parser.add_argument("--max-candidates", type=int, default=8)
    lint_plan_parser.add_argument("--max-chars-per-page", type=int, default=2500)
    lint_plan_parser.add_argument("--max-tokens", type=int, default=None)
    lint_plan_parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    lint_plan_parser.set_defaults(handler=run_lint_plan)

    contracts_parser = subparsers.add_parser("contracts", help="List known semantic contracts.")
    contracts_parser.add_argument("--json", action="store_true", help="Print contracts as JSON.")
    contracts_parser.set_defaults(handler=run_contracts)

    run_contract_parser = subparsers.add_parser("run-contract", help="Run one semantic contract with the configured model.")
    run_contract_parser.add_argument("contract", help="Semantic contract name, such as source_normalize or lint_diagnose.")
    run_contract_parser.add_argument("--input", required=True, help="Path to a JSON input payload.")
    run_contract_parser.add_argument("--provider", default=None, help="Model provider name. Defaults to models.default_provider.")
    run_contract_parser.add_argument("--temperature", type=float, default=0.1)
    run_contract_parser.add_argument("--max-tokens", type=int, default=None)
    run_contract_parser.set_defaults(handler=run_contract)

    return parser


def add_vault_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault", default=None, help="Path to the Obsidian wiki vault. Overrides config.yaml.")


