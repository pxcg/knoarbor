from __future__ import annotations

"""Public HTTP API compatibility contract.

This module is the single machine-readable list of routes that are intended to
remain stable across 1.x releases. Tests, documentation checks, and release
readiness scripts should read this contract instead of duplicating route lists.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiRouteSpec:
    method: str
    path: str
    request_schema: str = ""
    response_schema: str = ""
    error_envelope: str = "public_error.v1"


PUBLIC_STABLE_ROUTE_SPECS: tuple[ApiRouteSpec, ...] = (
    ApiRouteSpec("GET", "/health", response_schema="health.v1"),
    ApiRouteSpec("GET", "/doctor", response_schema="doctor.v1"),
    ApiRouteSpec("POST", "/ingest", request_schema="ingest_request.v1", response_schema="workflow_response.v1"),
    ApiRouteSpec("POST", "/lint", request_schema="lint_request.v1", response_schema="workflow_response.v1"),
    ApiRouteSpec("GET", "/models/providers", response_schema="model_providers.v1"),
    ApiRouteSpec("POST", "/models/discover", request_schema="model_discover_request.v1", response_schema="model_discover_response.v1"),
    ApiRouteSpec("POST", "/models/probe", request_schema="model_probe_request.v1", response_schema="model_probe_response.v1"),
    ApiRouteSpec("POST", "/models/apply-capabilities", request_schema="model_capability_apply_request.v1", response_schema="model_capability_apply_response.v1"),
    ApiRouteSpec("POST", "/chat", request_schema="chat_request.v1", response_schema="chat_response.v1"),
    ApiRouteSpec("POST", "/chat/stream", request_schema="chat_request.v1", response_schema="chat_stream.v1"),
    ApiRouteSpec("GET", "/chat/sessions", response_schema="chat_sessions.v1"),
    ApiRouteSpec("GET", "/chat/sessions/{session_id}", response_schema="chat_session.v1"),
    ApiRouteSpec("PATCH", "/chat/sessions/{session_id}", request_schema="chat_session_update.v1", response_schema="chat_session.v1"),
    ApiRouteSpec("DELETE", "/chat/sessions/{session_id}", response_schema="delete_response.v1"),
    ApiRouteSpec("POST", "/chat/sessions/{session_id}/ingest", request_schema="chat_session_ingest_request.v1", response_schema="workflow_response.v1"),
    ApiRouteSpec("POST", "/chat/sessions/{session_id}/close", response_schema="chat_session.v1"),
    ApiRouteSpec("POST", "/chat/sessions/{session_id}/retry", request_schema="chat_retry_request.v1", response_schema="chat_response.v1"),
    ApiRouteSpec("POST", "/query", request_schema="wiki_query_request.v1", response_schema="wiki_query_response.v1"),
    ApiRouteSpec("POST", "/query/feedback", request_schema="query_feedback_request.v1", response_schema="query_feedback_response.v1"),
    ApiRouteSpec("GET", "/query/trends", response_schema="query_trends.v1"),
    ApiRouteSpec("GET", "/reports", response_schema="reports.v1"),
    ApiRouteSpec("GET", "/reports/content", response_schema="report_content.v1"),
    ApiRouteSpec("GET", "/runtime", response_schema="runtime_context.v1"),
    ApiRouteSpec("GET", "/sources", response_schema="source_catalog.v1"),
    ApiRouteSpec("GET", "/vaults", response_schema="vaults.v1"),
    ApiRouteSpec("GET", "/runs", response_schema="runs.v1"),
    ApiRouteSpec("GET", "/runs/{run_id}", response_schema="run_record.v1"),
    ApiRouteSpec("GET", "/runs/{run_id}/events", response_schema="run_events.v1"),
    ApiRouteSpec("GET", "/runs/{run_id}/stream", response_schema="run_event_stream.v1"),
    ApiRouteSpec("POST", "/runs/{run_id}/cancel", response_schema="run_record.v1"),
    ApiRouteSpec("GET", "/wiki/pages", response_schema="wiki_pages.v1"),
    ApiRouteSpec("GET", "/wiki/pages/content", response_schema="wiki_page_content.v1"),
    ApiRouteSpec("GET", "/wiki/pages/relations", response_schema="wiki_page_relations.v1"),
)


PUBLIC_STABLE_ROUTES: tuple[str, ...] = (
    tuple(dict.fromkeys(spec.path for spec in PUBLIC_STABLE_ROUTE_SPECS))
)

UI_PUBLIC_ROUTES: tuple[str, ...] = (
    "/ui",
    "/ui/assets/{asset_path}",
    "/ui/api/config",
    "/ui/api/config/form",
    "/ui/api/config/diagnostics",
    "/ui/api/status",
    "/ui/api/graph",
    "/ui/api/tokens",
    "/ui/api/docs/{doc_path}",
    "/ui/{asset_path}",
)

def stable_route_set() -> set[str]:
    return set(PUBLIC_STABLE_ROUTES)


def stable_route_specs() -> tuple[ApiRouteSpec, ...]:
    return PUBLIC_STABLE_ROUTE_SPECS


def ui_route_set() -> set[str]:
    return set(UI_PUBLIC_ROUTES)
