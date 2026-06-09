# 1.6 Productized Console Design

## Owning Layers

| Layer | Responsibility |
| --- | --- |
| UI | Navigation, presentation, local component state, vault-scoped cache keys. |
| Services | UI-only config forms, diagnostics summaries, docs previews, report previews. |
| Public API | Workflow execution, runs, query, wiki page reads, reports, sources. |
| Backend Core | Source discovery, workflow policy, report generation, page reads. |

## UI Boundary

The console may call:

- stable public APIs for workflows, runs, reports, wiki pages, sources, query,
  and doctor;
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

Primary surfaces:

- Dashboard / overview.
- Sources and settings.
- Runs.
- Reports.
- Wiki pages and graph.
- Query.
- Token and cost analysis.
- Project docs.

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
