# 1.6 Productized Console Design

## Owning Layers

| Layer | Responsibility |
| --- | --- |
| UI navigation owner | Active surface, one-shot typed destination target, workspace vault selection, and visited-surface retention. |
| UI pages | Presentation, page-local controls, and local interaction state. |
| Services | UI-only config forms, diagnostics summaries, docs previews, report previews. |
| Public API | Workflow execution, runs, query, wiki page reads, reports, sources. |
| Backend Core | Source discovery, workflow policy, report generation, page reads. |

## UI Boundary

The console may call:

- stable public APIs for workflows, runs, reports, wiki pages, sources, query,
  and vaults;
- `/ui/api/*` only for local-console specific adapters such as config forms,
  bundled docs, and UI diagnostics.

The console must not:

- decide ingest/lint policy;
- parse generated wiki pages through a second implementation when `/wiki/*`
  exposes the same data;
- silently repair malformed backend payloads;
- run hidden diagnostics on every page navigation.

## Product Information Architecture

The console should answer:

- What is configured?
- What is running?
- What changed?
- What can I read or query?
- What needs attention?

Primary surfaces are Chat, Flows, and Knowledge. Flows owns run monitoring,
ingest, lint, query, reports, and token analysis. Knowledge owns
Wiki pages and graph. Settings is a workspace modal rather than a retained
route, and there is no separate overview route.

Source capability has no separate renderer workspace: Settings owns connector
configuration and diagnostics, Ingest owns configured-source selection and run
submission, and Knowledge owns Raw/provenance inspection. The public source
catalog remains an input to those owners rather than a user-facing page owner.

## Navigation And Workspace State

`appNavigation` is the single renderer authority for navigation commands and
typed destination targets. A destination identity contains its view, vault ID,
target kind, and target path or ID. Pages consume their target once and retain
their own selected row, filter, query, or conversation state afterward. A
target consumer waits until its authoritative collection is ready, then ends
the request as resolved, not found, or explicitly superseded by a local user
selection. Every terminal result consumes the target; missing destinations are
reported inside the owning page rather than silently falling back to another
record.

Wiki-page navigation does not treat a cached page collection as proof that a
target was deleted. It reads the requested target through the backend page
resolver and reports deletion only for an authoritative 404. A pending
materialized view remains a distinct rebuildable state. Every terminal ingest
run invalidates the matching vault's page, graph, and query caches by run
identity; cache correctness does not depend on observing an active-run-count
transition.

Visited renderer routes remain mounted but inactive routes are hidden and
removed from the accessibility tree. This keeps page-local state and active
Chat streaming state intact. Queries, polling, target resolution, and automatic
detail reads remain gated by the active view, so retained hidden pages do not
perform background work.

Vault-scoped pages render a shared page-local vault switcher in their own tool
area. The switchers do not own separate vault truth: they call the shared
workspace-vault owner, which always resolves to one concrete vault. Chat owns a
separate retrieval scope that may be either one concrete vault or the virtual
all-vault scope.

The primary Chat navigation button only opens the retained Chat workspace.
Explicit plus buttons and the desktop New Chat command issue the same typed
new-session target. Changing Chat retrieval scope or opening a cross-page Chat
prompt starts a new session in that scope before applying the prompt; a
persisted session is never reused under a different scope.

Run navigation carries `vault_id`, `run_id`, and flow. The destination resolves
the exact persisted run before rendering it, reports a local not-found state,
and never substitutes the latest run. Chat run/report citations must carry
their originating vault identity rather than falling back to the current
workspace vault.

## Component Strategy

Prefer shared local primitives first:

- page shell and section headers;
- cards and list rows;
- status badges;
- report summary renderer;
- Markdown preview;
- diff viewer;
- metric tiles;
- empty/error/loading states.

The shared Markdown contract includes GFM plus inline `$...$` and block
`$$...$$` TeX rendering through KaTeX. Raw, Wiki, reports, citation preview,
and Chat answers reuse that renderer configuration and bundled stylesheet;
formula rendering does not enable arbitrary Markdown HTML.

Adopt an external component library only if custom primitives continue to
create repeated layout and accessibility debt.

## Rejected Alternatives

### Make UI A Workflow Engine

Rejected because Python Core owns workflow behavior and reports.

### Render Raw JSON As The Main UI

Rejected because users need readable summaries first. Raw JSON/Markdown belongs
in collapsible details.

### Run Full Diagnostics On Every Page Load

Rejected because it makes navigation slow and surprising. Expensive diagnostics
should be explicit refresh actions or cached summaries.

## Modal Submission Errors

The page launcher hook owns the operation error. Opening or cancelling the
custom-input dialog clears that state. While the dialog is open it is the sole
visible error boundary; after it closes, page-level operations retain the
existing page error boundary. The dialog receives the mapped message and does
not introduce its own request state, mapper, toast, or fallback.
