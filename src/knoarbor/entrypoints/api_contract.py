from __future__ import annotations

"""Public HTTP API compatibility contract.

This module is the single machine-readable list of routes that are intended to
remain stable across v0.x releases. Tests, documentation checks, and release
readiness scripts should read this contract instead of duplicating route lists.
"""

PUBLIC_STABLE_ROUTES: tuple[str, ...] = (
    "/health",
    "/doctor",
    "/ingest",
    "/lint",
    "/query",
    "/query/feedback",
    "/query/trends",
    "/reports",
    "/reports/content",
    "/runtime",
    "/runs",
    "/runs/{run_id}",
    "/runs/{run_id}/events",
    "/runs/{run_id}/stream",
    "/runs/{run_id}/cancel",
    "/wiki/pages",
    "/wiki/pages/content",
    "/wiki/pages/links",
)

UI_PUBLIC_ROUTES: tuple[str, ...] = (
    "/ui",
    "/ui/assets/{asset_path}",
    "/ui/api/config",
    "/ui/api/config/form",
    "/ui/api/config/diagnostics",
    "/ui/api/status",
    "/ui/api/graph",
    "/ui/api/docs/{doc_path}",
    "/ui/{asset_path}",
)

def stable_route_set() -> set[str]:
    return set(PUBLIC_STABLE_ROUTES)


def ui_route_set() -> set[str]:
    return set(UI_PUBLIC_ROUTES)
