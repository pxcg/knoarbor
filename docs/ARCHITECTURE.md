# Architecture

This document is the public architecture overview for KnoArbor. It explains the stable system boundaries without exposing internal planning notes. The Chinese architecture overview lives in [zh/ARCHITECTURE.md](zh/ARCHITECTURE.md).

KnoArbor is an AI-native wiki engine that compiles multi-source information into a traceable, maintainable knowledge network.

```text
raw source -> ingest canonical facts -> indexes/projections -> lint integrity -> raw-grounded query/chat
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

The executable architecture gate enforces downward dependencies for core,
storage, runtime, pipelines, and renderer domain modules. File length can
trigger a responsibility review, but it is never an automatic failure or split
rule. A module is extracted only when behavior has a distinct owner, contract,
dependency set, lifecycle, or independently testable policy.

| Layer | Owns | Must not own |
| --- | --- | --- |
| Entry | CLI, FastAPI, Web UI, skills, and external workflow adapters. | Prompt contracts, page write policy, source classification, or vault mutation rules. |
| Pipeline | `ingest`, `lint`, and `query` orchestration. | Low-level model HTTP calls, file rendering details, or UI presentation state. |
| Connector / Source | Converting Markdown, chats, documents, and future external systems into `SourceDocument`. | Semantic extraction, factual publication, projection, or page lifecycle governance. |
| Document Processing | Converting rich documents into Markdown before shared ingest. | Knowledge-object classification or wiki writes. |
| Semantic | Narrow LLM contracts, prompts, schema validation, and semantic workflow steps. | Reading local files, writing pages, executing operations, or managing progress. |
| Model Gateway | Stable model boundary, ProviderAdapter selection, OpenAI-compatible and Ollama-native calls, JSON mode, endpoint checks, retry, and token metrics. | Ingest/lint/query decisions. |
| Storage / Writer | Immutable factual revisions, SQLite source heads and cursors, materialization, index updates, and low-level vault file primitives. | Deciding whether a knowledge object should exist or how reports are summarized. |
| Retrieval / Index | Knowledge-atom ranking, claim resolution, exact source-unit evidence resolution, navigation indexes, and query context packs. | Mutating the wiki or treating projections as factual authority. |
| Maintenance | Canonical integrity scans, read-only semantic findings, automatic owner-routed repair, post-repair verification, and audit. | Direct raw/fact mutation or generated-page content authoring outside owner workflows. |
| Runtime | Queue, run monitor, heartbeat, event catalog, cancellation, file locks, and logs. | Business semantics or retry decisions outside the semantic runner. |
| Config / Policy | Runtime paths, model providers, connectors, privacy, execution limits, and feature switches. | Hidden behavior not visible through configuration. |
| Report / Audit | Human-readable reports, machine ledgers, failure reports, query records, run summaries, and report rendering. | Source of truth for page content or maintenance execution decisions. |
| Wiki Chat | Linear console question-answer flow over Query evidence, citations, and explicit product capabilities. | Generic shell/browser/file/network automation, iterative research loops, or hidden workflow policy. |
| Memory | Long-lived chat preferences, vault-specific interaction conventions, explicit memory candidates, recall context, and memory events. | Wiki knowledge pages, raw source archives, source records, or arbitrary chat transcript storage. |

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
- `vaults/default/raw/inbox/chats/`: normalized AI tool sessions such as Hermes, Codex, OpenClaw, or Claude Code.
- `vaults/default/raw/derived/markdown/`: Markdown generated by deterministic preprocessors such as a user-managed MinerU-compatible service.
- `vaults/default/raw/derived/excerpts/`: user-selected short excerpts.
- `vaults/default/raw/derived/assets/`: extracted images, tables, pages, and media attachments.
- `vaults/default/raw/derived/metadata/`: source-adjacent metadata that should not be rendered as wiki pages.
- `vaults/default/artifacts/`: user-visible chat or tool artifacts such as generated images.

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
- `.knoarbor/facts/<source>/<revision>/`: immutable source, knowledge, diagnostics, and integrity files selected by SQLite source heads.
- `.knoarbor/ingest.sqlite`: durable task, attempt lease, source head/cursor,
  contribution, and vault materialization authority.
- UI browsing views are derived from the verified machine-index generation
  selected by `.knoarbor/index/CURRENT`; they are not written as wiki facts.

Knowledge-page structure is expressed inside each Markdown page: identity,
summary, claims, entities, relations, evidence, and synthesis. Physical
directories are not used as knowledge types.

Human-readable reports stay in `vaults/default/maintenance/reports/`. Machine state, runs,
ledgers, source cursors, locks, and indexes stay in `vaults/default/.knoarbor/`.
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

- immutable machine-index generations under `vaults/default/.knoarbor/index/generations/`, with `.knoarbor/index/CURRENT` atomically selecting the verified active generation;
- machine-readable page, relation, and source views served for UI navigation;
- local field-weighted BM25 over active claim, entity, relation, and Raw locator documents;
- one verified cross-source relation adjacency over canonical entity IDs, with every edge closed through its supporting claims to active Raw;
- exact claim-evidence resolution into active raw source units;
- query context packs for host AI tools.

The persisted generation format can evolve behind the same publication and
query contracts:

```text
active atom batches + processing records
  -> deterministic index generation
  -> verified CURRENT snapshot
  -> lexical recall + optional bounded relation traversal + exact evidence resolution
```

Workflow code depends on stable retrieval payloads and the verified snapshot,
not on provider classes without a production caller or a human-maintained
`index.md`.

The retrieval snapshot is normalized derived state: parent Raw rerank text is
stored once per evidence identity, while locator rows retain only search and
active-resolution metadata. A Query batch verifies one immutable snapshot per
vault and shares it across its expressions and evidence reads. Complete Raw and
semantic facts remain outside the index in their existing authorities.

### Query Evidence Selection

Default query fuses claim/atom and Raw lexical recall. For code-classified
relational intent, it additionally enumerates deterministic simple paths of at
most two active relation edges, then resolves every supporting claim to active
Raw. It does not merge page ranking into factual evidence ranking.
Projection paths remain optional navigation metadata in one locator list.
Complete selected source units are the only factual material in query and chat
context.

### Governance Layer

The governance layer records why the wiki changed.

It includes:

- SQLite source cursor and task state;
- ingest reports;
- lint reports;
- failed-run reports;
- operation ledgers;
- quality and verification output.

Automated maintenance must be inspectable. A page update should have a visible source, reason, risk signal, and execution result.

Failed workflow runs are also audit events. If ingest, lint, or query fails before a normal result exists, the service layer should write a failure report and ledger entry whenever a vault path is available. The runtime queue records status; audit owns the user-readable failure artifact.

### Memory Layer

The memory layer stores durable interaction preferences used by the Wiki Chat
Agent. Memory is separate from wiki pages and source records:

- wiki pages record stable knowledge objects;
- source records record provenance summaries;
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
  -> semantic atom extraction
  -> deterministic validation, merge, and entity linking
  -> immutable factual revision and active-head commit
  -> deterministic source projection and machine-index materialization
  -> report and ledger
```

Responsibilities:

- connectors discover and normalize source-specific material into shared `SourceDocument` contracts;
- source input separates discovery (`SourceRef`), raw state (`RawSource`), normalized content (`SourceDocument`), processing identity (`SourceFingerprint`), and checkpoint windows; connector or parser version changes re-enter processing even when source bytes are unchanged;
- long-source segmentation belongs after `SourceDocument` normalization and
  before semantic extraction; segment results are merged deterministically at
  the source/window boundary;
- the model produces semantic candidates while code owns evidence binding,
  identities, validation, entity linking, publication, projection, and
  diagnostics;
- a structured processing record and evidence-backed atom batch are committed
  as one immutable factual revision selected by the SQLite source head;
- `wiki/pages/` source projections and machine indexes are model-free,
  rebuildable materializations rather than factual authorities;
- ingest no longer writes source-record Markdown under `wiki/sources/`;
- broad lexical navigation links are retrieval signals rather than persisted
  factual relationships;
- `ingest --input` is the one-off local input boundary: Markdown files and folders enter the shared ingest path directly; non-Markdown files must pass through the configured MinerU-compatible preprocessor first, and missing preprocessors fail explicitly.

Implementation boundary:

- `services.ingest_coordinator` is the only public submit and recovery boundary.
- `services.ingest_input_resolver` resolves source requests and freezes immutable input generations.
- `runtime.transactional_ingest` owns durable task/attempt state, source heads,
  cursors, entity contributions, and materialization epochs.
- `storage.revision_integrity` owns immutable factual-revision manifest and file
  verification without importing the lifecycle store.
- `storage.index_snapshot` owns immutable machine-index generation lookup and
  verification without importing index writers or runtime lifecycle owners.
- `runtime.ingest_executor` executes one persisted local task and coordinates
  provider admission, factual processing, and one materialization attempt.
- `runtime.ingest_session` is the pipeline port for lease renewal and factual
  publication.
- `pipelines.ingest_auto` owns redaction, unitization, conditional segmentation,
  semantic metadata extraction, one deterministic compiler-integrity boundary,
  and source-level result reporting.
- `pipelines.source_segmentation` owns context-budget segment planning.
- `pipelines.ingest_metrics` owns source/segment and semantic metrics.
- `storage.source_revisions` owns immutable factual-revision publication;
- `storage.materialization` owns deterministic source projection and immutable
  machine-index generation publication.
- `storage.wiki_projection` owns readable source projection rendering.

### Lint

Goal: verify the raw-to-projection dependency chain without becoming a second
knowledge writer.

```text
canonical collection
  -> deterministic integrity scan
  -> optional read-only semantic diagnosis/review
  -> owner-routed rebuild, reingest, or report requests
  -> report and ledger
```

Responsibilities:

- validate projection contracts, canonical atom references, evidence identity,
  and machine-index publication;
- rebuild only derived machine indexes through deterministic publication code;
- route canonical extraction defects to `reingest_request`;
- route generated-view drift to `projection_rebuild_request`;
- keep ambiguous, external, privacy, merge, and graph-policy findings report-only;
- keep semantic diagnosis read-only: models produce evidence-backed findings,
  never page drafts or replacement facts.

Implementation boundary:

- `lint_collection` owns page collection, wikilink lookup maps, graph health, and scoped page expansion.
- `lint_scanners` owns deterministic scan rules and issue generation.
- `lint_candidates` owns evidence-bound quality and temporal-signal selection
  without fixed page-length or candidate-count cutoffs.
- `WikiLintPipeline` owns scan, optional semantic review, repair orchestration,
  post-repair scan, and audit artifacts.
- `lint_execution` deduplicates repair actions and invokes ingest or
  materialization; it never patches page content directly.

User-facing modes:

- `deterministic`: integrity scan, automatic derived-state repair, and rescan.
- `semantic`: the same repair semantics plus read-only model diagnosis and review;
  approved canonical quality findings trigger automatic reingest.

### Query

Goal: return claim-backed active raw evidence for Chat or a host AI, not
generate the final answer.

```text
query
  -> active lexical retrieval
  -> optional canonical-entity relation traversal (at most two edges)
  -> all supporting claims
  -> exact active source-unit resolution
  -> raw-grounded context pack
  -> trace and gap signals
```

Responsibilities:

- return ranked atom/claim trace, raw evidence/source units, source pointers, optional projection locators, and a raw-grounded context pack;
- explain retrieval through match reasons, matched terms, and trace data;
- use wiki page prose, summaries, claims, entities, and relations as locator metadata, not final factual answer material;
- never mutate wiki pages;
- never claim that related pages are weaker or stronger evidence than direct pages; `match_kind` only explains retrieval origin.

Retrieval signals:

- field-weighted BM25 ranking across active claim, entity, relation, and Raw
  locator documents;
- query normalization removes conversational scaffolding only, preserves
  content-bearing domain nouns, technical identifiers, and CJK
  phrase/bigram/trigram terms;
- entity expansion through claim entity references and relation expansion through `source_claim_ids`;
- Relation atoms remain in the atom/claim lexical channel and close through batch-local `source_claim_ids` to active Raw;
- Query derives a compact document/top-level-chapter outline with one complete
  source-level synthesis per document and dominant language hints from active
  source processing and atom records; Chat's optional Retrieval Planner selects
  visible regions and writes one standalone regional expression but never
  selects a retrieval algorithm or judges candidates;
- exact claim evidence edges into active raw source units; Raw lexical ranking remains an independent extraction-miss channel;
- one 12-parent BM25/RRF result window per Chat region group, followed by
  vault-scoped Raw deduplication, one 16-parent global result window,
  exact-span structural validation, and bounded Raw evidence assembly.

### Wiki Chat Agent

Goal: let the console user ask the selected vault in natural language while
keeping all actions inside KnoArbor-owned boundaries.

```text
chat request
  -> Query-derived locator-only document/chapter outline
  -> one dialogue-aware Retrieval Planner
     (exact visible region IDs + one regional expression)
  -> one active-Raw Query batch with literal + regional expressions grouped
     inside selected regions
  -> one Answer Decision
     (authority, Raw support, source visuals, partial gap, generated-image prompt)
  -> optional generated-image provider call
  -> one Response Composer
     (reader-facing wording, structure, language, and all image positions)
  -> deterministic support, citation, and image validation
  -> provenance-bearing turn persistence
```

Responsibilities:

- synthesize answers inside the management console;
- execute `retrieve_knowledge_batch` through the same Query-owned active-Raw
  retrieval contracts used by `/query`;
- preserve the unchanged question in every selected region group and optionally
  invoke the Retrieval Planner once before the Query batch;
- run each selected document/chapter region through ordinary Query recall and
  constrain only that expression's candidates to its active source units;
- never seed or force-admit Raw from region membership;
- give Answer Decision the original question, dialogue-only history, typed
  retrieval outcome, current Raw evidence, visual semantics, and runtime
  capability; planner rewrites stay locator-only;
- let Query own the BM25/RRF result window and structural evidence selection
  while Chat forwards returned evidence
  without a second ranking, filtering, truncation, or context-length budget;
- let Answer Decision semantically choose one whole-response Raw-grounded,
  general-knowledge, or knowledge-gap mode and select exact support and source
  visuals, plus a generated-image prompt only for explicit create-new intent;
  code validates rather than routes that authority;
- invoke any authorized image generation after Answer Decision, persist its
  output, and project only request-local generated-visual semantics and typed
  status to Response Composer;
- map the validated selection to call-local materials and give Response
  Composer one code-owned reader-facing source label, exact source-ordered Raw
  texts, and selected visual semantics;
- let Response Composer own reader-facing language, requested format,
  structure, partial-gap wording, and exact source/generated visual positions
  without reconsidering relevance;
- reject mixed grounded/general blocks until block-level provenance is an
  explicit public contract;
- expose complete active Raw units plus code-issued sentence/structural-line
  support spans to Answer Decision, validate selected span IDs, and retain
  their private mapping to public citations; retrieval match spans remain
  locator metadata;
- prepare one selected-material projection for Response Composer with
  request-local material IDs, code-owned source labels, exact source-ordered
  Raw text, selected call-local visual references, source captions, and
  extracted visual content. Code
  retains support IDs, filenames, durable attachment/revision identities,
  offsets, filesystem paths, and attachment Markdown, accepts natural Markdown
  structures under one explicit material mapping, and renders every selected
  visual exactly once in an owner-adjacent single or contiguous visual group;
- project complete substantive dialogue while removing code-rendered citation
  markers, source/generated image Markdown, and generated-image labels before
  any semantic model call; history resolves references but never supplies
  facts;
- expose citations and evidence trace to the UI.
- expose image generation as a capability to Answer Decision; only its
  non-null `generated_image_prompt` invokes the provider, and Response Composer
  then places successful generated visuals inside the normal Chat mainline;
- persist each assistant turn with its own citations, tool trace, events,
  memory metadata, and stats;
- convert an explicitly selected stored chat session into a `knoarbor_chat`
  source document and queue ingest through the shared run manager.

Boundaries:

- `/query` remains model-free evidence retrieval for host AI tools;
- Chat orchestration receives explicit memory, session, tool, execution, and
  ingest-workflow capabilities rather than the full application service
  container;
- conversation-message identity and merge behavior are owned by
  `services.chat_messages` and reused by context assembly and persistence;
- Chat does not receive arbitrary shell, browser, filesystem, or network tools;
- Chat does not write wiki markdown directly;
- workflow behavior remains in ingest/lint services and run manager.

## Local Runtime Infrastructure

KnoArbor remains a local-first wiki engine, but it still needs explicit runtime infrastructure. These concerns are architecture layers, not scattered safeguards inside individual endpoints.

- **Machine index layer**: program-readable page, relation, link, source, and navigation metadata. The durable boundary is one verified generation selected by `.knoarbor/index/CURRENT`; `index.md` is optional export material rather than source of truth. Default knowledge query reads active atoms and explicit evidence edges. Future providers may persist that same atom/edge contract without changing query semantics.
- **Local ingest operation lifecycle**: persisted task/attempt state,
  cancellation, recovery assessment, and source publication live in
  `TransactionalIngestStore`. `LocalOperationScheduler` submits work once in the
  desktop process; the CLI may execute the same persisted task in its foreground
  process. SQLite claim fencing permits only one owner.
- **Run events**: long workflows emit structured events for stages, model calls, retries, page writes, query results, and failures. UI, CLI, reports, and skills consume the same event stream instead of reconstructing progress from ad hoc logs.
- **Recovery**: semantic recovery creates a new attempt under the immutable
  ingest command and input generation. Materialization recovery reads committed
  facts and never invokes a model. Run files and reports are projections of
  durable state, not recovery authority.
- **Single-machine execution**: local operations may overlap outside the vault
  mutation boundary. Provider calls use bounded admission; segment calls may use
  configured bounded concurrency. All factual and materialization mutations use
  the cross-process vault write lock and transactional publication boundaries.
- **Runtime logs**: diagnostics are written to `.knoarbor/logs/knoarbor.log`. Logs are for operators and developers; user-facing reports, ledgers, and run events remain separate artifacts.
- **File locks**: all local vault mutations use `.knoarbor/locks/vault.write.lock`. This protects pages, indexes, logs, SQLite publication, ledgers, and maintenance writes from concurrent local processes. It is a single-machine consistency boundary, not a distributed lock.
- **Semantic retry policy**: model retries belong to `SemanticRunner`, not to ingest, lint, API routes, or prompt-specific cleanup code. The runner may retry errors in the configured retryable error-code allowlist, emits retry/failure events, and records failed attempts in semantic metrics. Page writes still happen only after the owning source or reviewed maintenance batch succeeds.
- **Execution recovery**: recovery creates a new attempt from the immutable replay request only after the complete execution manifest still matches. Committed SQLite source/window cursors remain authoritative, so successful unchanged sources are skipped and changed execution semantics require a new task.
- **Event model**: run events are progress facts such as `source_started`, `segment_finished`, `model_call_started`, `model_call_retrying`, and `pages_written`. The frozen catalog lives in `knoarbor.runtime.events`; new event names should be added there before pipelines emit them. UI/API consumers display these facts but must not derive new business decisions from events.
- **Application cache**: no separate app cache layer is required for the first release. Page parse results, graph data, and query indexes are cacheable later; source cursors, lint decisions, ledgers, and reports are not replaceable by cache.
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

- Index Metadata Extract Agent: extracts `entities`, `relations`, `claims`, and `synthesis` for raw-grounded ingest.
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
- UI is a management console for configuration, running, reports, wiki browsing, and graph inspection; it is not a separate workflow engine.

## Frontend Boundaries

The web UI is a local management console over the public and UI-only HTTP adapters. It should keep product interaction clear without becoming a second implementation of the backend.

Responsibilities:

- present configuration, source status, runs, reports, wiki pages, and graph data;
- call stable core APIs for workflow execution, run state, query context, and wiki page reads;
- call the machine-readable `UI_PUBLIC_ROUTES` adapter set only for UI-specific
  concerns such as config forms, diagnostics summaries, local assets, and
  presentation summaries;
- render Markdown, diffs, reports, and graph views with reusable local components.
- maintain a UI-side Vault Runtime state for active vault selection, vault-scoped cache keys, and multi-vault display state.
- keep `api/client.ts` as a composition surface over domain clients with one
  shared HTTP/SSE transport and error boundary;
- consume the Electron preload bridge through the preload-owned type contract;
- give page and feature modules explicit application capability slices while
  reserving the complete application context for controller and route
  composition roots.

Non-responsibilities:

- source discovery, source-cursor logic, segmentation, projection editing, lint execution, retry policy, vault writes, and report generation;
- parsing wiki pages through a separate UI-only code path when a core `/wiki/*` read API exists;
- silently repairing malformed API payloads that should have been validated by Python Core.

The Vault Runtime is a frontend state boundary, not a storage layer. It maps configured vault profiles to stable UI identities, keeps React Query caches partitioned by `vaultId`, and passes the resolved vault path to API calls. This lets the UI switch active vaults without clearing unrelated page state and prepares future multi-vault views where several vault summaries can be shown side by side.

The current renderer keeps a lightweight local component system instead of adopting a full UI component framework. If forms, menus, dialogs, tables, and report views continue to grow, the next architectural step should be extracting shared UI primitives or adopting a small component library deliberately, not adding page-specific styling patches.

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
