# UI Contract

This document freezes the current UI-facing product surfaces for the local web
console and desktop shell. It describes what each surface displays and which
data contract it consumes.

## Surface Model

KnoArbor uses a chat-first interface with secondary workspaces.

| Surface | Purpose | Primary data |
| --- | --- | --- |
| Chat | Ask maintained wiki pages and continue sessions | chat sessions, evidence packs, citations |
| Flows | Run and inspect workflows | runs, reports, ingest/lint/query requests |
| Knowledge | Browse maintained pages and graph views | wiki pages, graph index, page content |
| Settings | Configure vaults, inputs, preprocessing, models, runtime | config form, diagnostics, models |

## Chat

Chat displays:

- a global conversation list;
- vault-scoped conversation groups;
- the selected conversation;
- the selected model;
- the selected vault scope for the message;
- answer text, inline references, citation controls, and follow-up suggestions.

Global chat uses all configured vaults as the retrieval scope. Vault-scoped chat
uses one vault as the retrieval scope and stores the session under that vault's
runtime chat state.

Chat consumes the chat service contract:

```text
session -> turns -> tool trace -> evidence pack -> answer -> citations
```

## Flows

Flows groups workflow pages:

- run monitor;
- ingest;
- lint;
- query;
- reports;
- token analysis.

Workflow pages use run records and reports as the source of truth. A workflow
page may present the latest result inline, but the durable record is stored in
`maintenance/reports/**` and `.knoarbor/runs/**`.

## Knowledge

Knowledge groups:

- maintained wiki pages from `wiki/pages`;
- source audit pages from `wiki/sources` when the view is explicitly source or
  provenance oriented;
- page graph views derived from the wiki index provider.

The default page browser displays maintained wiki pages. Source digests are
shown through provenance/source-audit views, graph side panels, reports, and
citations.

Graph views:

- Page graph: nodes are wiki/source pages; edges are page links or semantic
  page-neighborhood edges exposed by the index provider.

## Settings

Settings configures:

- vault profiles;
- input sources;
- document preprocessing;
- model providers and probes;
- runtime limits;
- diagnostics;
- advanced YAML.

Settings changes are written through config services. UI components call API
or service adapters; they do not write config files directly.

## UI-Only API Adapters

Routes under `/ui/api/*` are bundled UI adapters. They can aggregate public API,
config, local asset serving, diagnostics, and report helpers for the console.

External integrations use the public API in `docs/API_COMPATIBILITY.md`.

## Rendering Rules

- Wiki pages render the frozen page sections in order.
- Source digest pages render audit sections in order.
- Attachment tables wrap long text and use readable labels.
- Raw asset paths and parser metadata are hidden from default page rendering
  unless the user opens an audit/source detail view.
