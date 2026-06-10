# 1.6 Productized Console Tasks

## Loading And State

- [done] Audit page-load API calls and remove hidden expensive scans.
- [done] Gate status, reports, recent runs, multi-vault overview, and source
  catalog requests by the pages that actually need them.
- [done] Define shared stale/refresh behavior for config, runtime state,
  reports, wiki pages, graph, and query trends.
- [later] Add page-level loading budgets and smoke checks.

## Component Consolidation

- [done] Inventory duplicated cards, report views, Markdown previews, and diff views.
- [done] Extract shared page-link and report-summary primitives where ownership is clear.
- [later] Evaluate a small component library only after duplication is measured.

## Reports And Runs

- [done] Ensure ingest/lint report summaries expose changed pages, written
  pages, related pages, failures, and diffs through one shared report view.
- [done] Improve report filters by flow and vault.
- [done] Link run completion states to report detail consistently.

## Sources And Settings

- [done] Move settings out of primary navigation into a single workspace
  settings modal that hosts the full configuration workbench directly.
- [later] Use source catalog metadata to reduce connector-specific UI hardcoding.
- [later] Improve connector settings editing without exposing irrelevant advanced fields.

## Deferred

- [deferred] Hosted multi-user UI.
- [deferred] Chat interface.
- [deferred] Full design system package.
