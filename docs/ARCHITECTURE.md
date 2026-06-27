# Architecture

This document is the public architecture overview for KnoArbor. It explains the stable system boundaries without exposing internal planning notes. The Chinese architecture overview lives in [zh/ARCHITECTURE.md](zh/ARCHITECTURE.md).

KnoArbor is an AI-native wiki engine that compiles multi-source information into a traceable, maintainable knowledge network.

```text
raw source -> source document -> ingest -> wiki pages -> lint -> query context
```

## Design Goals

KnoArbor is not a chat archive and not a raw-document search tool.

It is designed around four principles:

- keep raw sources immutable;
- compile useful material into durable Markdown wiki pages;
- maintain page structure, links, provenance, and quality over time;
- query the maintained wiki rather than repeatedly reasoning over raw files.

The operating model is:

```text
compile once, maintain continuously, retrieve from the maintained artifact
```

## Architecture Layer Taxonomy

KnoArbor changes should first be assigned to one architecture layer. This keeps
workflow behavior, model behavior, storage, and runtime observability from
leaking into each other.

| Layer | Owns | Must not own |
| --- | --- | --- |
| Entry | CLI, FastAPI, Web UI, skills, and external workflow adapters. | Prompt contracts, page write policy, source classification, or vault mutation rules. |
| Pipeline | `ingest`, `lint`, and `query` orchestration. | Low-level model HTTP calls, file rendering details, or UI presentation state. |
| Connector / Source | Converting Markdown, chats, documents, and future external systems into `SourceDocument`. | Wiki page planning or page lifecycle governance. |
| Document Processing | Converting rich documents into Markdown before shared ingest. | Knowledge-object classification or wiki writes. |
| Semantic | Narrow LLM contracts, prompts, schema validation, and semantic workflow steps. | Reading local files, writing pages, executing operations, or managing progress. |
| Model Gateway | Stable model boundary, ProviderAdapter selection, OpenAI-compatible and Ollama-native calls, JSON mode, endpoint checks, retry, and token metrics. | Ingest/lint/query decisions. |
| Storage / Writer | Markdown rendering, patch application, index updates, checkpoints, and low-level vault file primitives. | Deciding whether a knowledge object should exist or how reports are summarized. |
| Retrieval / Index | Page metadata, field-weighted BM25 ranking, link graph, related expansion, query context packs, and future durable/vector providers. | Mutating the wiki. |
| Maintenance | Deterministic scans, semantic lint candidates, operation execution, and verification. | Raw source ingestion or audit artifact ownership. |
| Runtime | Queue, run monitor, heartbeat, event catalog, cancellation, file locks, and logs. | Business semantics or retry decisions outside the semantic runner. |
| Config / Policy | Runtime paths, model providers, connectors, privacy, execution limits, and feature switches. | Hidden behavior not visible through configuration. |
| Report / Audit | Human-readable reports, machine ledgers, failure reports, query records, run summaries, and report rendering. | Source of truth for page content or maintenance execution decisions. |
| Wiki Chat Agent | Bounded console conversation loop over KnoArbor tools, citations, and workflow entry points. | Generic shell/browser/file/network automation or hidden workflow policy. |
| Memory | Long-lived chat preferences, vault-specific interaction conventions, explicit memory candidates, recall context, and memory events. | Wiki knowledge pages, raw source archives, source digests, or arbitrary chat transcript storage. |

Implementation notes:

- CLI keeps `cli.py` as the entry/error boundary. Command registration lives in `cli_commands/parser.py`; command behavior lives in `cli_commands/handlers.py`.
- UI configuration keeps request/response schemas in `services/ui_config_models.py`; `services/ui_config.py` owns config read/write, form conversion, and diagnostics.
- Maintenance verification keeps orchestration in `maintenance/operation_verification.py`; action-specific verification rules live in `maintenance/operation_verifiers.py`.
- Report modules share primitive Markdown formatting helpers through `audit/report_formatting.py`; ingest and lint reports still own their workflow-specific summaries.

Granularity rule:

- Split a module when it mixes different architectural layers, has separately testable policies, or forces unrelated imports into callers.
- Keep a module together when it is a cohesive registry, command-handler set, verifier-rule set, or report renderer whose main cost is local length rather than unclear ownership.
- Prefer one clear file with local helper functions over many tiny files that make a workflow harder to trace.
- New subpackages should describe a durable concept, not just hide a long function.

## System Layers

### Source Layer

The source layer keeps original material and source-derived normalized documents.

Typical runtime directories:

- `vaults/default/raw/inbox/notes/`: user-provided Markdown notes.
- `vaults/default/raw/inbox/documents/`: original rich documents such as PDF, DOCX, PPTX, XLSX, manuals, and course material.
- `vaults/default/raw/inbox/media/`: original images and media files.
- `vaults/default/raw/normalized/chats/`: normalized AI tool sessions such as Hermes, Codex, OpenClaw, or Claude Code.
- `vaults/default/raw/normalized/markdown/`: Markdown generated by deterministic preprocessors such as a user-managed MinerU-compatible service.
- `vaults/default/raw/normalized/excerpts/`: user-selected short excerpts.
- `vaults/default/raw/assets/`: extracted images, tables, pages, and media attachments.
- `vaults/default/raw/sidecars/`: source-adjacent metadata that should not be rendered as wiki pages.

Rules:

- LLM workflows never overwrite raw sources.
- Source identity is tracked through path and content hash.
- Chat sources use checkpoint windows so only newly appended turns are processed.
- Rich documents are converted to Markdown before entering the shared ingest path.

### Knowledge Layer

The knowledge layer stores maintained wiki content under `vaults/default/wiki/`.
Open `vaults/default/wiki` in Obsidian when you want a clean vault without raw
sources, reports, or machine state:

- `wiki/pages/<slug>.md`: maintained knowledge pages.
- `wiki/sources/*.md`: source digest and provenance audit pages.
- UI browsing views are derived from `.knoarbor/index/manifest.json` and
  `.knoarbor/index/graph_index.json`; they are not written as wiki facts.

Knowledge-page structure is expressed inside each Markdown page: identity,
summary, claims, entities, relations, evidence, and synthesis. Physical
directories are not used as knowledge types.

Human-readable reports stay in `vaults/default/maintenance/reports/`. Machine state, runs,
ledgers, checkpoints, locks, and indexes stay in `vaults/default/.knoarbor/`.
Auditable claims and typed relations are page-internal structures and machine-indexed atoms,
not standalone page directories.

Rules:

- Each wiki page should represent one stable knowledge object.
- Page boundaries matter more than preserving source shape.
- Prefer a small number of useful pages over many thin fragments.
- `maintenance/`, `raw/`, and `.knoarbor/` are not wiki page targets.

### Index Layer

The index layer provides routing and retrieval context for agents and query flows.

Current implementation:

- machine index artifacts under `vaults/default/.knoarbor/index/`, with `manifest.json` and `graph_index.json` as the durable graph boundary;
- machine-readable page, relation, source, and search views served through the index provider for UI/query services;
- local Markdown retrieval with field-weighted BM25 over title, path, entities, summary, claims, relations, headings, and body;
- graph expansion through claim-backed entity relations, source relationships, and machine-index page context;
- query context packs for host AI tools.

Long-term direction:

```text
IndexProvider
  -> MarkdownIndexProvider
  -> SQLite FTS provider
  -> Vector provider
  -> Hybrid provider
```

Workflow code should depend on stable retrieval payloads and graph index artifacts, not on a human-maintained `index.md`.

### Response Evidence Selection

The answer set selection layer turns ranked page candidates into an answer
plan. It selects primary pages, supporting pages, source pages, further reading,
and rejected candidates with reasons. This layer is deterministic and does not
call a model.

The selector sits after page-level BM25/link expansion and before context pack
or chat evidence packaging. It is the main guard against RAG-style noise: the
retriever may recall broadly, but only selected answer-bearing pages shape the
default response.

### Governance Layer

The governance layer records why the wiki changed.

It includes:

- checkpoints;
- ingest reports;
- lint reports;
- failed-run reports;
- operation ledgers;
- quality and verification output.

Automated maintenance must be inspectable. A page update should have a visible source, reason, risk signal, and execution result.

Failed workflow runs are also audit events. If ingest, lint, or query fails before a normal result exists, the service layer should write a failure report and ledger entry whenever a vault path is available. The runtime queue records status; audit owns the user-readable failure artifact.

### Memory Layer

The memory layer stores durable interaction preferences used by the Wiki Chat
Agent. Memory is separate from wiki pages and source digests:

- wiki pages record stable knowledge objects;
- source digests record provenance summaries;
- memory records guide how the chat surface should use knowledge for a user or
  vault.

Memory files live under `vaults/default/.knoarbor/memory/`:

- `records.jsonl`: append-only memory records;
- `candidates.jsonl`: proposed or auto-written memory candidates;
- `events.jsonl`: recall and write events;
- `profile.md`: optional human-readable profile summary.

The chat layer recalls memory before model calls and captures only explicit
low-risk preferences in the first implementation. Inferred session summaries,
global memory, and manual candidate review are planned extensions.

## Main Workflows

### Ingest

Goal: turn new or changed source material into coordinated wiki page operations.

```text
connector discovery
  -> source normalization
  -> privacy redaction
  -> checkpoint window
  -> source segmentation
  -> source normalize agent
  -> source digest audit projection + atom extraction
  -> source-level aggregation
  -> candidate page retrieval
  -> page planning
  -> claim / relation / evidence closure
  -> deterministic page assembly
  -> page-local prose generation
  -> deterministic write gate
  -> conditional semantic draft review
  -> ingest write policy
  -> wiki write
  -> machine index + atom index
  -> scoped deterministic lint
  -> checkpoint commit
  -> report and ledger
```

Responsibilities:

- connectors discover and normalize source-specific material into shared `SourceDocument` contracts;
- source input separates discovery (`SourceRef`), raw state (`RawSource`), normalized content (`SourceDocument`), processing identity (`SourceFingerprint`), and checkpoint windows; connector or parser version changes re-enter processing even when source bytes are unchanged;
- ingest decides how the current source enters the wiki;
- ingest supports `create`, `update`, and `skip`;
- merge, archive, delete, rename, and cross-page lifecycle governance belong to lint/maintenance;
- long-source segmentation belongs after `SourceDocument` normalization and before semantic ingest;
- segmented sources are processed segment by segment, then aggregated at the source/window boundary before write, report, and checkpoint commit.
- `IngestWritePolicy` enforces source/window-level write invariants before vault writes: one raw source may create at most one source digest in one ingest batch.
- source digest pages are provenance audit views generated from source units, selected atoms, write results, warnings, and raw pointers. They are not ordinary knowledge pages and are not authored by the page draft agent.
- ordinary wiki page structure is claims-first: selected claims determine linked entities, relation triples, evidence rows, and the readable synthesis layer.
- ingest writes do not persist broad lexical navigation links. Provenance is carried by source digest Contribution Maps, page evidence/source trace, and machine indexes; weak topical links stay in retrieval/query results.
- `ingest --input` is the one-off local input boundary: Markdown files and folders enter the shared ingest path directly; non-Markdown files must pass through the configured MinerU-compatible preprocessor first, and missing preprocessors fail explicitly.

Implementation boundary:

- `pipelines/ingest.py` is the orchestration shell: connector execution, segment execution, report coordination, and checkpoint commit.
- `pipelines/ingest_checkpoint.py` owns checkpoint planning, checkpoint commit payloads, and the checkpoint-commit eligibility rule. Checkpoints advance only after approved writes or a source-level semantic skip.
- `pipelines/source_segmentation.py` owns segment planning and source-window chunk boundaries.
- `pipelines/ingest_semantic.py` owns the semantic ingest agent chain: source normalization, atom extraction, candidate retrieval, page planning, page-local prose generation, and conditional draft review.
- `pipelines/ingest_context.py` owns candidate page retrieval and materialization.
- `pipelines/ingest_postprocess.py` owns the deterministic write/report/index boundary after approval: approved draft write commits, generated page recording, atom-index updates, and source-scoped deterministic lint.
- `pipelines/ingest_metrics.py` owns source/segment metrics, redaction aggregation, and semantic token statistics.
- `pipelines/ingest_lifecycle.py` owns missing/moved source lifecycle candidates emitted from checkpoint state.
- `pipelines/ingest_write_gate.py` and `pipelines/ingest_write_policy.py` own pre-persistence validation and write invariants.

### Lint

Goal: maintain already generated wiki pages.

```text
scan
  -> diagnose
  -> review / policy
  -> execute
  -> verify / rescan
  -> report and ledger
```

Responsibilities:

- scan deterministic page structure, links, provenance, and contract issues;
- diagnose structural, provenance, quality, freshness, and graph candidates;
- review necessity, correctness, completeness, risk, confidence, and executor fit;
- execute only reviewed operations;
- keep high-risk refresh, merge/split, conflict, and external-fact work as queued or report-only actions unless explicitly supported by a reviewed executor.
- route reviewed decisions through explicit executor paths:
  - `supported_by_wiki_operation` -> `WikiOperationPipeline` -> verification;
  - `supported_by_draft_write` -> draft compilation -> `WikiWritePipeline` -> verification;
  - `supported_by_report_only` -> deferred retry with enriched page context -> wiki operation or draft write when evidence becomes sufficient; otherwise it remains queued in the report;
  - `supported_by_refresh_request` -> provenance refresh -> source digest creation or source/knowledge bidirectional link repair -> rescan.

Implementation boundary:

- `lint_collection` owns page collection, wikilink lookup maps, graph health, and scoped page expansion.
- `lint_scanners` owns deterministic scan rules and issue generation.
- `lint_candidates` owns scan-page previews and quality/freshness candidate scoring.
- `WikiLintPipeline` is the internal deterministic maintenance pipeline for scan, candidate selection, safe fixes, and lint report generation. Public callers enter through the unified `/lint` API or CLI `lint` command.
- `lint_execution` owns decision-to-executor routing and must not implement source parsing or page rendering directly.
- `provenance_refresh` owns refresh-request execution. It only handles local raw sources that can be resolved inside the vault and repairs the raw source -> source digest -> generated page chain. Missing or ambiguous sources remain queued with warnings.

User-facing modes:

- `structural`: structure, links, and provenance maintenance;
- `quality`: focused semantic quality review;
- `full`: structural and quality maintenance in one run.

### Query

Goal: return wiki context for a host AI, not generate the final answer.

```text
query
  -> page retrieval
  -> related expansion
  -> answer-bearing page bodies plus provenance structure
  -> page-first context pack
  -> trace and gap signals
```

Responsibilities:

- return ranked pages, answer-bearing page bodies, source pointers, related context, and a page-first context pack;
- explain retrieval through match reasons, matched terms, and trace data;
- never mutate wiki pages;
- never claim that related pages are weaker or stronger evidence than direct pages; `match_kind` only explains retrieval origin.

Retrieval signals:

- field-weighted BM25 page ranking across title, path, entities, summary, claims, relations, headings, and body;
- query terms preserve technical identifiers and CJK phrase fragments when possible;
- related page expansion through source relationships, shared entities, typed relations, and graph proximity;
- graph relevance boosts for shared source, entities, and relation affinity;
- bounded context assembly for host AI tools.

### Wiki Chat Agent

Goal: let the console user ask the selected vault in natural language while
keeping all actions inside KnoArbor-owned boundaries.

```text
chat request
  -> bounded evidence planning loop
  -> retrieval policy adjustment
  -> guarded KnoArbor tool execution
  -> canonical evidence packages
  -> answer synthesis
  -> answer with citations and evidence trace
```

Responsibilities:

- synthesize answers inside the management console;
- plan and execute bounded KnoArbor tools such as `query_wiki`,
  `read_wiki_page`, `reuse_context`, `answer_directly`, and `finish_answer`;
- repeat evidence gathering within `max_turns` when coverage is weak, a primary
  page is missing, or a known page needs full detail;
- enforce code-owned guardrails so knowledge questions use wiki evidence;
- treat model tool plans as proposals and apply `ChatRetrievalPolicy` before
  execution, so context-synthesis follow-ups reuse prior session evidence
  instead of drifting into broad literal searches;
- build a canonical page-first evidence package before model synthesis;
- expose citations and evidence trace to the UI.
- persist each assistant turn with its own citations, tool trace, events,
  memory metadata, and stats;
- convert an explicitly selected stored chat session into a `knoarbor_chat`
  source document and queue ingest through the shared run manager.

Boundaries:

- `/query` remains model-free evidence retrieval for host AI tools;
- Chat does not receive arbitrary shell, browser, filesystem, or network tools;
- Chat does not write wiki markdown directly;
- workflow behavior remains in ingest/lint services and run manager.

## Local Runtime Infrastructure

KnoArbor remains a local-first wiki engine, but it still needs explicit runtime infrastructure. These concerns are architecture layers, not scattered safeguards inside individual endpoints.

- **Machine index layer**: program-readable page, relation, link, source, and retrieval metadata. The default durable boundary is `.knoarbor/index/manifest.json` plus `.knoarbor/index/graph_index.json`; `index.md` is optional export material rather than source of truth. The current implementation uses Markdown scanning, graph index artifacts, index-provider views, and page-level BM25 scoring; future providers can materialize SQLite FTS or vector indexes behind the same `IndexProvider` boundary.
- **Run queue and lifecycle**: queued execution, status transitions, heartbeat timestamps, cancellation requests, recovery metadata, and run events live in the runtime layer. Pipelines report progress through this boundary and do not write run-state files directly.
- **Run events**: long workflows emit structured events for stages, model calls, retries, page writes, query results, and failures. UI, CLI, reports, and skills consume the same event stream instead of reconstructing progress from ad hoc logs.
- **Recovery**: recoverable runs are derived from stored run metadata and reports. Recovery creates a new run with scoped input rather than mutating or resuming a finished run record in place.
- **Single-machine queue**: `LocalRunQueue` is the first queue backend. It is process-local, filesystem-observable, and serializes runs per vault. It reuses `run_id`, run records, events, cancellation, and reports from `RunMonitor`. The queue owns task scheduling; pipelines own business logic.
  - Runs for the same vault are serialized because ingest, lint, checkpoint, ledger, index, and page writes share one consistency boundary.
  - Runs for different vaults can proceed independently.
  - Model providers may allow concurrent API calls. KnoArbor supports bounded source concurrency for dry-run/preflight ingest, but write-capable ingest remains serial inside one vault. Future write-capable concurrency must aggregate semantic drafts before writing and commit checkpoints only after the full source succeeds.
- **Runtime logs**: diagnostics are written to `.knoarbor/logs/knoarbor.log`. Logs are for operators and developers; user-facing reports, ledgers, and run events remain separate artifacts.
- **File locks**: all local vault mutations use `.knoarbor/locks/vault.write.lock`. This protects pages, indexes, logs, checkpoints, ledgers, and maintenance writes from concurrent local processes. It is a single-machine consistency boundary, not a distributed lock.
- **Semantic retry policy**: model retries belong to `SemanticRunner`, not to ingest, lint, API routes, or prompt-specific cleanup code. The runner may retry errors in the configured retryable error-code allowlist, emits retry/failure events, and records failed attempts in semantic metrics. Page writes still happen only after the owning source or reviewed maintenance batch succeeds.
- **Execution recovery**: recovery is represented as a new run derived from previous run metadata. Source/window checkpoints remain authoritative, so successful unchanged sources are skipped and failed or changed sources re-enter the normal ingest pipeline.
- **Event model**: run events are progress facts such as `source_started`, `segment_finished`, `model_call_started`, `model_call_retrying`, and `pages_written`. The frozen catalog lives in `knoarbor.runtime.events`; new event names should be added there before pipelines emit them. UI/API consumers display these facts but must not derive new business decisions from events.
- **Application cache**: no separate app cache layer is required for the first release. Page parse results, graph data, and query indexes are cacheable later; write checkpoints, lint decisions, ledgers, and reports are not replaceable by cache.
- **Provider prompt cache**: prompt caching is owned by the model provider. `SemanticRunner` builds every call as a `SemanticPromptPackage`: stable executor instructions plus stable contract text first, then the dynamic source/wiki payload last. The runner must not inject timestamps, run IDs, local paths, or other volatile data into the stable prefix. Provider cache telemetry such as cached prompt tokens or DeepSeek cache hit/miss tokens is collected when available, and prompt package size metrics are recorded for later cost analysis.
- **Docker**: Docker is a deployment adapter, not a core architecture layer. It should package the Python Core, CLI/FastAPI entrypoints, static UI, and config templates after the local execution path is stable.

## Read API Boundaries

Generated wiki pages have their own stable read boundary:

```text
storage / retrieval metadata
  -> WikiPagesService
  -> /wiki/pages, /wiki/pages/content, /wiki/pages/relations
  -> UI, skills, CLI wrappers, external clients
```

The UI must not own separate page-reading logic. It may own UI-only adapters such as configuration forms, project documentation previews, and report list rendering, but generated wiki page listing, page detail, and page relation reads belong to the `wiki` API/service boundary.

## Agent Boundaries

KnoArbor uses narrow semantic contracts rather than autonomous multi-agent teams.

- Source Normalize Agent: converts `SourceDocument` into `knowledge_extract.v1`.
- Relation Agent: plans page-level create/update/skip operations.
- Draft Compile Agent: writes coordinated drafts and patches for approved operations.
- Ingest Draft Review Agent: reviews write safety before ingest writes.
- Lint Diagnose Agents: convert scan/quality evidence into maintenance candidates.
- Maintenance Review Agent: approves, defers, or rejects maintenance candidates.
- Query is retrieval-first and does not use an answer-generation agent.
- Wiki Chat Agent is the console-only bounded answer agent over KnoArbor tools.

Agents do not read files, write pages, execute operations, or repair malformed upstream output. Python Core owns orchestration, writes, ledgers, and reports.

## API And Adapter Boundaries

- Python Core is the long-term execution path.
- FastAPI is an HTTP adapter over Python Core.
- CLI is an execution adapter over the same pipelines.
- External workflow tools are optional adapters and should call stable pipeline-level APIs.
- UI is a management console for configuration, running, reports, docs, and graph inspection; it is not a separate workflow engine.

## Frontend Boundaries

The web UI is a local management console over the public and UI-only HTTP adapters. It should keep product interaction clear without becoming a second implementation of the backend.

Responsibilities:

- present configuration, source status, runs, reports, wiki pages, graph data, and project documentation;
- call stable core APIs for workflow execution, run state, query context, and wiki page reads;
- call `/ui/api/*` only for UI-specific adapters such as config forms, diagnostics summaries, bundled docs, and report previews;
- render Markdown, diffs, reports, and graph views with reusable local components.
- maintain a UI-side Vault Runtime state for active vault selection, vault-scoped cache keys, and multi-vault display state.

Non-responsibilities:

- source discovery, checkpoint logic, segmentation, page operation planning, lint execution, retry policy, vault writes, and report generation;
- parsing wiki pages through a separate UI-only code path when a core `/wiki/*` read API exists;
- silently repairing malformed API payloads that should have been validated by Python Core.

The Vault Runtime is a frontend state boundary, not a storage layer. It maps configured vault profiles to stable UI identities, keeps React Query caches partitioned by `vaultId`, and passes the resolved vault path to API calls. This lets the UI switch active vaults without clearing unrelated page state and prepares future multi-vault views where several vault summaries can be shown side by side.

For the 1.x line, KnoArbor keeps a lightweight local component system instead of adopting a full UI component framework. If forms, menus, dialogs, tables, and report views continue to grow, the next architectural step should be extracting shared UI primitives or adopting a small component library deliberately, not adding page-specific styling patches.

## Reliability Principles

- fix root causes at the owning layer;
- prefer schemas, contracts, validators, and explicit executors over fallback logic;
- do not infer missing business decisions in writer, router, API, CLI, or UI layers;
- keep automated writes visible in reports and ledgers;
- add operations only when evidence, parameters, executor support, and verification are clear.

## Related Documents

- [Core Concepts](CONCEPTS.md)
- [Provenance Design](PROVENANCE_DESIGN.md)
- [Configuration](CONFIGURATION.md)
- [Development](DEVELOPMENT.md)
