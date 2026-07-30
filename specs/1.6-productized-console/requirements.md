# 1.6 Productized Console Requirements

## Problem

KnoArbor's local console has grown from a developer control panel into a core
user surface. It now needs clearer navigation, faster loading, better report
reading, better source/vault configuration, and consistent product design.

The 1.6 line should make the console usable for non-developer workflows without
turning it into a separate workflow engine.

## Goals

- Make navigation and page hierarchy obvious.
- Avoid expensive scans during page navigation.
- Present runs, reports, wiki pages, graph, source configuration/import, and
  token usage through their owning surfaces in a product-quality way.
- Keep UI state aligned with public API and UI-only adapters.
- Reuse shared UI components for Markdown, reports, diffs, cards, and status.
- Render inline and block TeX formulas in Raw, Wiki, report, citation-preview,
  and Chat Markdown through the same safe KaTeX pipeline.
- Keep UI logic out of backend decisions.
- Preserve each visited workspace's local interaction state while users move
  between Chat, Flows, Knowledge, reports, and diagnostics.
- Give every vault-scoped page its own visible knowledge-base switcher while
  reusing one interaction contract and one workspace-vault authority.

## Non-Goals

- Do not build a chat assistant surface.
- Do not duplicate backend ingest/lint/query logic in React.
- Do not make `/ui/api/*` a public integration API.
- Do not adopt a large component framework unless it clearly reduces custom
  complexity.

## User Scenarios

### First Run

As a new user, I can open the console, understand what to configure, and run a
first ingest without reading internal docs.

Acceptance criteria:

- First-run state is visible.
- Settings and source status are understandable.
- Errors link to actionable guidance.

### Inspect A Completed Run

As a user, I can see what an ingest or lint run produced without manually
searching the vault.

Acceptance criteria:

- Reports show written pages, changed pages, diffs, and links.
- Page previews reuse the wiki page rendering component.
- Failed runs still have readable reports.

### Navigate The Knowledge Base

As a user, I can browse vault pages, graph relationships, and page content
without layout jumps or repeated slow scans.

Acceptance criteria:

- Page lists and graph views share stable vault selection.
- UI caches are scoped by vault.
- Manual refresh is explicit when data may be stale.
- Wiki, graph, ingest, lint, reports, tokens, and other vault-scoped
  pages expose the same page-local knowledge-base switch interaction.
- Cross-page links carry the destination vault and cannot reopen a same-path
  page or report from another vault.

### Move Between Workspaces

As a user, I can leave an in-progress Chat, query, page, graph, or report view
and return without the navigation action silently resetting that workspace.

Acceptance criteria:

- ordinary page switching preserves the previously visited page state;
- a primary Chat navigation action returns to Chat without creating a session;
- explicit new-chat actions, including the desktop shortcut, share one
  new-session command;
- one-shot cross-page targets do not reactivate after the user has navigated
  elsewhere inside the destination page;
- a destination target is consumed after success, not-found, or local
  supersession, and a missing destination produces page-local feedback instead
  of selecting a different record;
- a terminal ingest invalidates page, graph, and query caches for its vault
  without relying on an observed active-run-count transition;
- Wiki navigation resolves the requested target through the backend page
  reader, reports deletion only for an authoritative 404, and presents
  materialization pending as a rebuildable knowledge-view state;
- hidden retained workspaces issue no polling, target-resolution, or automatic
  detail requests;
- changing Chat scope or opening a cross-page Chat prompt starts a fresh
  session in the requested scope;
- workflow completion and Chat run links open the exact persisted run identified
  by vault, run ID, and flow rather than the latest run.
- workflow launch failures remain on the initiating page and render a safe,
  actionable local error instead of existing only in the developer console;
- at supported narrow desktop window sizes, Chat keeps the message stream and
  composer inside the viewport with the send action reachable.

## Current Status

Implemented:

- Local console served by `knoar serve`.
- Vault selection and multi-vault UI state.
- Runs, reports, wiki pages, graph, settings modal, query, and token pages.
- Source configuration and diagnostics in Settings, configured-source execution
  in Ingest, and Raw/provenance inspection in Knowledge.
- UI-only config and diagnostics adapters.

Still in scope for 1.6:

- Productize page layout and loading strategy.
- Reduce component duplication.
- Improve report and diff readability.
- Decide whether to introduce shared UI primitives or a component library.

## Initiating Dialog Error Ownership

When an asynchronous action is initiated from an open modal dialog, a mapped
failure MUST be visible inside that dialog while it remains open. The page and
dialog MUST share one error state and one mapping authority; the same failure
must not render simultaneously behind the modal or in a duplicate notice.
