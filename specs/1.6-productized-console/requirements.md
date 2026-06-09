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
- Present runs, reports, wiki pages, graph, sources, and token usage in a
  product-quality way.
- Keep UI state aligned with public API and UI-only adapters.
- Reuse shared UI components for Markdown, reports, diffs, cards, and status.
- Keep UI logic out of backend decisions.

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

## Current Status

Implemented:

- Local console served by `knoar serve`.
- Vault selection and multi-vault UI state.
- Runs, reports, wiki pages, graph, sources, settings, docs, query, token pages.
- UI-only config and diagnostics adapters.

Still in scope for 1.6:

- Productize page layout and loading strategy.
- Reduce component duplication.
- Improve report and diff readability.
- Decide whether to introduce shared UI primitives or a component library.
