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
| Settings modal | Configure vaults, inputs, preprocessing, models, runtime | config form, diagnostics, models |

## Chat

Chat displays:

- a global conversation list;
- complete, scrollable vault-scoped conversation groups, including older
  persisted sessions reached through summary pagination;
- the selected conversation;
- the selected model;
- the selected vault scope for the message;
- the automatically selected answer source and its persisted provenance;
- answer text, inline references, citation controls, and follow-up suggestions.

The conversation list remains mounted in the primary sidebar while the user
visits Flows or Knowledge, so secondary workspace navigation does not remove
conversation orientation or require an intermediate return to Chat.

Global chat uses all configured vaults as the retrieval scope. Vault-scoped chat
uses one vault as the retrieval scope and stores the session under that vault's
runtime chat state.

Chat retrieval scope is independent from the concrete workspace vault used by
non-Chat pages. Opening a Chat session never silently changes the knowledge
base selected by Knowledge, Flows, reports, or token analysis.

Changing Chat retrieval scope starts a new session in the selected scope.
Likewise, a cross-page Ask in Chat action starts a new scoped session before it
applies the prompt. Ordinary navigation back to Chat preserves the retained
conversation.

Chat consumes the chat service contract:

```text
session revision -> turns -> answer provenance -> Raw citations
```

Citation preview is owned by the selected conversation. Starting or opening a
different conversation closes the previous preview, and a late source response
from the previous conversation is ignored.

## Flows

Flows groups workflow pages:

- run monitor;
- ingest;
- lint;
- query;
- reports;
- token analysis.

Ingest accepts local files and folders, configured sources, saved chats, and
editable excerpts. Manual input and Chat selections open the same excerpt editor,
which owns the title, content, and target knowledge base before submitting the
public `kind=excerpt` request. A full saved-chat import remains a session-scoped
operation and uses the chat-session contract.

Workflow pages use run records and reports as the source of truth. A workflow
page may present the latest result inline, but the durable record is stored in
`maintenance/reports/**` and `.knoarbor/runs/**`.

Run, settings, query, chat, and knowledge feedback is rendered within the
owning surface. The application shell does not expose a cross-page global
notification area. Maintenance presents one user action; internally it runs
deterministic scanning before any model diagnosis, repair, and verification
required by the findings.

Every vault-scoped page exposes a knowledge-base switcher at the right edge of
its secondary-navigation row through the same shared UI primitive. Wiki,
graph, ingest, lint, reports, tokens,
and other single-vault views always resolve one concrete vault. Query
and Chat may expose an explicit all-vault scope where their API contract allows
it. Cross-page navigation carries the destination vault together with the page,
graph node, report, run, or session identity. A destination waits for its
authoritative data, then terminates as resolved, not found, or superseded by a
local selection. Missing targets produce local feedback and are never replaced
with the first or latest record. Retained hidden pages do not poll, resolve
targets, or automatically fetch details.

An ingest terminal record invalidates page, graph, and query caches for its
vault independently of active-run-count polling. Wiki navigation resolves its
target through the backend page reader; only an authoritative 404 is presented
as deleted. A `materialization_pending` result means facts are saved while the
page, graph, and search views await rebuild, and is presented as that
rebuildable state rather than as page deletion.

Reports operate only on the concrete vault selected by their page switcher and
do not expose a second all-vault filter. Run navigation resolves the exact
persisted record by vault, run ID, and flow. Report/run citations without vault
identity fail locally instead of falling back to the current workspace.

## Knowledge

Knowledge groups:

- maintained wiki pages from `wiki/pages`;
- source audit details from structured processing records when the view is
  explicitly source or provenance oriented;
- page graph views derived from the wiki index provider.

The default page browser renders the normalized source from the frozen input
generation as Raw, and the deterministic source projection under `wiki/pages`
as Extracted Results. Extracted Results inspect synthesis, claims, entities,
relations, and attachments. Claim evidence expands into a compact preview card
without exposing source-unit coordinates; selecting that card opens Raw at the
matching span with a temporary highlight. Raw is continuous Markdown, is not
rebuilt from source units, and does not display related-page sections.

Source units provide evidence coordinates only. The page action bar exposes a
single Raw/Extracted Results switch. Desktop builds may reveal the local source
in the system file manager without displaying its absolute path.

Reader-facing Markdown uses one bundled GFM and KaTeX pipeline. Inline
`$...$` and block `$$...$$` formulas render consistently in Raw, Wiki,
reports, citation preview, and Chat without loading remote assets or enabling
arbitrary HTML.

Chat displays one citation-source collection rather than a duplicate evidence
list. One inline marker represents one selected Raw source unit and its compact
locator retains every exact answer-selected range. The source collection groups
those Raw citations by document and reports both document and excerpt counts.
Selecting a document opens frozen Raw and highlights every cited range from
that document; selecting a Raw citation focuses its first range while retaining
the other highlights. Disjoint cited ranges remain distinct and unselected
retrieval candidates are never exposed as citations. Highlights remain until
the preview is closed or another citation is selected.
Citation records remain compact locators. The renderer requests temporary
highlight text from the Chat citation resolver when a source is opened; the
resolver reads the identified immutable source unit and does not persist the
text in the session. Source-unit-local offsets are never applied directly to
complete Raw. An unavailable locator opens without highlighting.

The editor for a `source_index` page renders only structured editable fields:
synthesis, existing claim text, entities, and relations. Claim evidence is
available as read-only context. Generated Markdown, identity fields, source,
attachments, and evidence coordinates never enter the edit form or request.
Saving submits a canonical projection-edit revision guarded by the revision that
opened the editor. It does not start ingest and applies only to that Raw
revision. A later Raw revision receives a fresh model-generated projection.

The Raw view exposes a separate Raw revision editor. Before saving, the UI
states that the current model will run again and that the new extraction will
replace the current projection. Saving submits a standard queued ingest and
navigates to its existing run monitor. It never overwrites a prior input
generation.

Graph views:

- Page graph: nodes are wiki/source pages; edges are page links or semantic
  page-neighborhood edges exposed by the index provider.

## Settings Modal

Settings configures:

- vault profiles;
- input sources;
- document preprocessing;
- model providers and probes;
- runtime limits;
- diagnostics;
- advanced YAML.

Settings changes are written through config services. UI components call API
or service adapters; they do not write config files directly. Settings has no
standalone retained route and opens only as the workspace modal.

There is no separate Sources workspace. Settings owns connector configuration
and diagnostics, Ingest owns selecting configured sources and starting a run,
and Knowledge owns Raw/provenance inspection.

## UI-Only API Adapters

The machine-readable `UI_PUBLIC_ROUTES` set owns bundled UI adapters such as
`/config`, `/config/form`, `/config/diagnostics`, `/vaults/status`,
`/wiki/graph`, `/tokens`, and `/vault-assets/*`. These routes may aggregate
configuration, local asset serving, diagnostics, and presentation helpers for
the console; their concrete paths are not stable external integration APIs.

External integrations use the public API in `docs/API_COMPATIBILITY.md`.

## Rendering Rules

- Raw renders the frozen normalized source without reconstructing it from
  source units.
- Extracted Results renders synthesis, claims, relations, entities, and
  attachments in a stable order.
- Claims show assertion text by default and expand source evidence on demand.
- Source record pages render audit sections in order.
- Attachment tables wrap long text and use readable labels.
- Raw asset paths and parser metadata are hidden from default page rendering
  unless the user opens an audit/source detail view.
