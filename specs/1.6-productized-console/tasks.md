# 1.6 Productized Console Tasks

## Loading And State

- [done] Audit page-load API calls and remove hidden expensive scans.
- [done] Gate reports, recent runs, source catalogs, target resolution, and
  automatic detail requests by the active pages that actually need them.
- [done] Define shared stale/refresh behavior for config, runtime state,
  reports, wiki pages, graph, and query trends.
- [later] Add page-level loading budgets and smoke checks.
- [done] Replace split focused-page/report/chat signals with one typed navigation
  target and consume it at the destination owner.
- [done] Retain visited route state without enabling hidden page data polling.
- [done] Unify primary Chat navigation and explicit desktop/sidebar new-chat
  commands.
- [done] Make every typed target terminate as resolved, not found, or locally
  superseded without substituting a different destination.
- [done] Reset the persisted Chat session before a scope change or cross-page
  prompt is applied.

## Component Consolidation

- [done] Inventory duplicated cards, report views, Markdown previews, and diff views.
- [done] Extract shared page-link and report-summary primitives where ownership is clear.
- [done] Add one bundled KaTeX pipeline for inline and block formulas across
  Raw/Wiki previews and Chat answers.
- [later] Evaluate a small component library only after duplication is measured.

## Reports And Runs

- [done] Ensure ingest/lint report summaries expose changed pages, written
  pages, related pages, failures, and diffs through one shared report view.
- [done] Keep report filtering within the concrete page-selected vault and
  filter that result by flow.
- [done] Link run completion states to report detail consistently.
- [done] Resolve targeted workflow results and Chat run links to the exact
  persisted run by vault, run ID, and flow.

## Settings And Input Ownership

- [done] Move settings out of primary navigation into a single workspace
  settings modal that hosts the full configuration workbench directly.
- [done] Remove the unreachable overview/settings routes and delete the residual
  Sources route whose accepted responsibilities already belong to Settings,
  Ingest, and Knowledge.
- [later] Use source catalog metadata to reduce connector-specific hardcoding in
  the remaining Settings and Ingest consumers.
- [later] Improve connector settings editing without exposing irrelevant advanced fields.
- [done] Add the shared page-local knowledge-base switcher to every vault-scoped
  console surface.

## Cross-Page Identity

- [done] Carry vault identity through Wiki, graph, report, and Chat citation
  navigation, including same-path reports from different vaults.
- [done] Add focused renderer tests for retained state, per-page vault switching,
  new-chat parity, and one-shot target consumption.

## Deferred

- [deferred] Hosted multi-user UI.
- [deferred] Chat interface.
- [deferred] Full design system package.

## Custom Input Error Root Fix

- [x] Render launch failures in the open custom-input dialog from the existing
  launcher error authority.
- [x] Clear modal-scoped failures on open and cancel and verify the error is not
  duplicated behind the modal.
