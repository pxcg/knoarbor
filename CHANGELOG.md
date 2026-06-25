# Changelog

All notable public changes to KnoArbor will be documented in this file.

This project follows a simple release-note format for public releases.

## 2.0.0 - 2026-06-25

### Added

- Added the first-class Electron desktop app surface, with managed service lifecycle, native menus, diagnostics, and app-data oriented startup behavior.
- Added document preprocessing support for richer ingest sources through the MinerU adapter.

### Changed

- Upgraded ingest planning, source digests, draft canonicalization, write gates, and report generation to support the desktop release and richer document flows.
- Refined the React console for the desktop shell and refreshed navigation, settings, run, wiki, and report surfaces.
- Synchronized package and runtime version metadata for the 2.0.0 release line.

### Validation

- `scripts/dev-check.sh`
- `scripts/release-readiness.py`
- `scripts/clean-clone-smoke.sh`

## Unreleased

Planned changes for the next release will be listed here.

## 1.3.0 - 2026-06-15

### Added

- Added a first-class vault registry API and CLI surface: `GET /vaults` and
  `knoar vaults list`.
- Added read-only CLI drilldown commands for maintained wiki pages and workflow reports: `knoar pages ...` and `knoar reports ...`.
- Added wiki-first chat planning so the assistant can query maintained pages,
  reuse prior evidence, read known pages, and synthesize grounded answers.
- Added model discovery improvements for local and OpenAI-compatible providers.

### Changed

- Updated the bundled host-AI skill to discover configured vaults through the
  public vault registry before selecting a knowledge base.
- Updated the management UI to load workspace choices from the public vault
  registry and to call public read/query/run APIs with `config_path + vault_id`
  where available.
- Moved the bundled host-AI skill package to `integrations/skills/knoarbor-local` and expanded its runtime discovery, multi-vault, page-read, report, ingest, and lint operation guidance.
- Added `schema_version: "workflow_response.v1"` to the stable `/ingest` and `/lint` workflow response envelope.
- Clarified that `/query` remains a direct retrieval endpoint returning `wiki_query.v1`, while `/ingest` and `/lint` use the workflow envelope.
- Updated CLI and API documentation for page/report read commands and workflow response contracts.
- Synchronized the Python package runtime version with `pyproject.toml`.
- Refined page-first retrieval so source digest pages are treated as provenance
  unless the user asks for source details.
- Refined the management console around chat, vault selection, query, and model
  settings.

### Validation

- Focused API, CLI, and skill tests pass.
- Ruff checks pass for modified Python modules and the bundled skill helper.

## 1.2.1 - 2026-06-10

### Added

- Added provider-level `context_window` and `max_output_tokens` settings for local and hosted OpenAI-compatible model providers.
- Added runtime context-window detection for vLLM-compatible `/v1/models` metadata.
- Added runtime context-window detection for Ollama via `/api/show` when `/v1/models` does not expose context metadata.
- Added model capability fields to doctor diagnostics and the settings UI.

### Changed

- Semantic ingest and lint now resolve output token limits from the selected provider before falling back to the global `models.default_max_tokens`.
- Updated model provider examples and installation/configuration documentation for Ollama and vLLM local runtimes.

### Validation

- Python unit test suite passes.
- Ruff checks pass for modified Python modules.
- Bundled management UI was rebuilt successfully.

## 1.2.0 - 2026-06-08

### Added

- Added first-class multi-vault profiles with stable vault IDs, display names, and paths.
- Added multi-vault query across all configured vaults or a selected vault set, with each result annotated by vault ID, name, and path.
- Added multi-vault run and report listing so operators can inspect workflow activity across configured knowledge bases.
- Added vault-aware write workflow selection for ingest and lint, while keeping each write run scoped to one vault.
- Added local skill metadata, icons, retrieval guidance, and natural-language command examples for host AI integrations.

### Changed

- Tightened CLI, API, UI, and skill semantics around `vault_id`, `vault_path`, and `config_path`.
- Improved local skill runtime discovery and follow-up page reads so selected query results can be opened from the same vault.
- Improved queued run responses so selected vault metadata is returned immediately after starting ingest or lint.
- Updated public API and CLI documentation for multi-vault read workflows and single-vault write workflows.

### Validation

- Development gate, release readiness, and clean-clone smoke checks are expected for the final release candidate.
- Live model validation should be run when a configured provider is available.

## 1.0.0 - 2026-06-03

### Added

- First public local-first release of KnoArbor.
- Added the full ingest, lint, and query workflow set behind stable CLI commands and stable HTTP endpoints.
- Added a bundled management console for source inspection, workflow runs, wiki browsing, graph viewing, reports, settings, and token analysis.
- Added a Knowledge Base browser for reading generated wiki pages, metadata, backlinks, outbound links, and workflow-linked results.
- Added runtime run monitoring with queue records, heartbeat events, cancellation, report links, and run history.
- Added a generic host-AI skill package for querying the local KnoArbor service from external AI tools.
- Added public API, CLI, configuration, troubleshooting, release, and bilingual README documentation.

### Changed

- Consolidated public workflow entrypoints around `knoar ingest`, `knoar lint`, `knoar query`, `/ingest`, `/lint`, and `/query`.
- Reworked the console navigation and reporting experience so run outputs link back to written or maintained wiki pages.
- Tightened the public API surface and removed prototype route assumptions from the release contract.
- Updated release readiness checks to keep runtime vault data, local configuration, caches, and workflow exports out of the published repository.

### Boundaries

- KnoArbor remains local-first and single-user for this release.
- KnoArbor does not bundle a chat answer generator, vector database, MinerU runtime, or model weights.
- Secrets stay in `.env`; runtime wiki data stays in the ignored `wiki/` vault.

## 0.9.0 - 2026-06-03

### Added

- Added runtime endpoint discovery through `.knoarbor/endpoint.json`, allowing local skills and tools to find the active service URL after `knoar serve` starts.
- Added automatic port selection for `knoar serve` when the configured port is already occupied.
- Added a more complete `knoarbor-local` skill package, including a reusable query helper, service check mode, examples, installation notes, security notes, and troubleshooting guidance.
- Added token ledger support and a Token Analytics console page for inspecting semantic model cost across reports.
- Added provenance refresh and recovery utilities used by maintenance workflows.

### Changed

- Improved the management console structure, run panels, report readability, Markdown preview behavior, settings layout, and localized labels.
- Improved query skill defaults so host AI tools receive a balanced context pack by default while still allowing full-page retrieval when requested.
- Improved semantic workflow reporting with clearer per-agent token metrics and cache-related fields.
- Updated CLI and quickstart documentation to describe the actual management UI URL, `/ui` alias, automatic port switching, and runtime endpoint file.

### Validation

- `scripts/dev-check.sh` passes: frontend build, frontend dependency audit, frontend e2e smoke, Python lint, documentation link check, 323 Python tests, CLI diagnostics, and Python package build.
- Live DeepSeek smoke was intentionally not run for this candidate because the model provider was unavailable during release preparation.

## 0.8.0 - 2026-06-01

### Added

- Added stable public API envelopes for `/ingest` and `/lint`, so queued and direct execution return the same top-level response shape.
- Added semantic token usage sections to ingest and lint reports, including per-agent call counts, prompt tokens, cached prompt tokens, cache rate, completion tokens, total tokens, elapsed time, and per-call details.
- Added prompt-cache-aware semantic execution preambles so stable contract instructions are separated from dynamic source payloads.

### Changed

- Standardized public API request fields around `vault_path` while keeping internal schema names private to the implementation.
- Tightened wiki page APIs into `/wiki/pages`, `/wiki/pages/content`, and `/wiki/pages/links`.
- Made run inspection APIs easier to call by allowing `/runs`, `/runs/{run_id}`, `/runs/{run_id}/events`, `/runs/{run_id}/stream`, and `/runs/{run_id}/cancel` to resolve the configured vault when `vault_path` is omitted.
- Updated API documentation and UI clients to use the stable `vault_path` contract.

## 0.7.0 - 2026-05-31

### Added

- Added `scripts/prepare-release.py` to synchronize release metadata and create release-note placeholders from a clean tree.
- Added explicit `wiki_query.v1` and `query_trace.v1` contract versions to query responses and trace payloads.
- Added a Knowledge Base page to the local console for browsing generated wiki pages, metadata, outbound links, backlinks, and page content.
- Added report artifacts that connect ingest outputs and lint changes back to concrete wiki pages.
- Added failure reports for ingest, lint, and query runs so failed workflows still leave inspectable diagnostics.

### Changed

- Upgraded the frontend build stack to Vite 8 and added `npm audit --audit-level=moderate` to the local development gate.
- Improved management console refresh/save feedback so manual refresh and YAML saves update visible UI state consistently.
- Refined the management console navigation, report readability, inline page expansion, and diff rendering.
- Hardened source provenance maintenance so scalar source fields stay valid while source sections may retain additional provenance lines.
- Removed internal maintainer planning documents from the public documentation tree and release line.

### Validation

- Rebuilt the bundled web console and ran Python maintenance/report tests before release.

## 0.5.1 - 2026-05-30

### Changed

- Extended the public error contract into run records, run events, semantic retry events, ingest source failures, ingest reports, CLI output, and UI API error messages.
- Added stable remediation hints for every public error code and preserved retryability metadata for monitor/report consumers.
- Added a machine-readable public API compatibility contract and tightened API surface tests against that contract.
- Converted unexpected FastAPI exceptions into the public `KA-INTERNAL-001` error envelope.
- Added UI recovery details for failed or partially failed ingest runs.
- Added a live release-candidate smoke test that validates Markdown ingest, Codex session ingest, lint, query, and missing-preprocessor errors against a real model provider.

### Validation

- Verified a temporary-vault live DeepSeek smoke: `init -> ingest -> lint-run -> query`, processing Markdown and Codex sources, writing four wiki pages, and checking the `KA-DOC-001` non-Markdown preprocessor path.
- `scripts/dev-check.sh` passes: frontend build, Python tests, read-only doctor, and package build.

## 0.5.0 - 2026-05-30

### Added

- Read-only readiness diagnostics through `knoar doctor` and `GET /doctor`, covering config loading, vault structure, model environment, connector discovery, optional document processing, and recent runs.
- Management UI readiness panel and run preflight view backed by the same `/doctor` contract used by CLI and API callers.
- Public API stability table for the v0.x alpha surface, clearly separating stable workflow/run/query/diagnostic routes from internal `/ui/api/*` routes.
- `doctor` checks in local development and clean-clone smoke gates.

### Changed

- Improved readable report labels for compact metric keys such as `runid`, `writtenpages`, and `tokenspersecond`.
- Clarified machine-index ownership: query, graph, UI page summaries, and UI status use machine index; deterministic lint keeps full-content maintenance scanning.
- Updated internal capability, roadmap, and engineering governance docs to align diagnostics, release gates, and machine-index boundaries.
- Synchronized runtime package version metadata.

### Validation

- Verified a temporary-vault live-model smoke with `examples/agent-loop.md`: `doctor -> ingest -> lint-run -> query`.
- `scripts/dev-check.sh` passes: frontend build, Python tests, read-only doctor, and package build.

## 0.4.0 - 2026-05-28

### Added

- Shared tolerant JSONL session reader for Codex, Claude Code, and OpenClaw connectors. Malformed or incomplete JSONL lines are skipped with connector warnings instead of failing the whole source preflight.
- Compact `sources --json` preflight output by default, with `--include-content` available when full normalized `SourceDocument.content` is intentionally needed.
- CLI progress policy for long human-facing workflows: `ingest`, `ingest-file`, and `lint-run` now follow local run progress by default, while `--json` remains machine-readable and `--no-follow` preserves synchronous summaries.
- `ingest-file` queue-follow support, so single-file Markdown or MinerU-preprocessed document ingest can surface run events and heartbeat progress like connector ingest.
- v0.4 ingest acceptance matrix for Markdown, Hermes, Codex, Claude Code, OpenClaw, and MinerU-preprocessed documents.

### Changed

- Strengthened multi-source ingest documentation around real local chat sources, source segmentation, and long-run progress.
- Unified lint service behavior with CLI behavior: structural lint can still run without a configured model provider when semantic structural mode has no model available.

### Validation

- Added and updated CLI and connector tests for compact source preflight, JSONL tolerance, queue-follow defaults, and structural lint fallback.
- Verified representative real-source preflight for Codex, Claude Code, and OpenClaw local session directories.
- Verified a write-capable smoke flow with Codex, Claude Code, and OpenClaw into a temporary vault, followed by lint and query.

## 0.3.0 - 2026-05-27

### Added

- Centralized semantic execution reliability through `SemanticRunner`, including retry policy, structured-output validation, error classification, run events, and token/latency metrics.
- Deterministic golden harnesses for query context packs, query reports, source segmentation, segmented ingest aggregation, lint scans, lint maintenance execution, operation verification, and lint run reports.
- Long-note and chat-session ingest quality golden datasets that lock source digest merging, page-boundary variety, written page links, and ingest report structure.
- Query gap trend visibility through API and the management UI.
- `scripts/release-check.sh` as the release gate wrapper for local gates, release readiness, and clean-clone smoke validation.

### Changed

- Refined v0.3 public API compatibility wording and release documentation around reliability and evaluation.
- Updated internal capability maps to make semantic contracts, harness coverage, and release gates explicit architecture boundaries.

## 0.2.0 - 2026-05-27

### Changed

- Started v0.2 engine-foundation work by refreshing stale machine indexes before index-backed readers use them.
- Moved graph and UI page-summary reads onto the machine-index boundary.
- Consolidated draft write indexing so batch writes update the index once at the pipeline boundary.
- Improved CLI error output to use the shared public error taxonomy.
- Formalized partial-failure run completion and richer query trace/report metadata.
- Routed FastAPI HTTP exceptions through the same public error envelope as service errors.
- Added a workflow result policy so background runs report partial completion when ingest or lint results contain failed sub-work.
- Updated the management UI to display localized run statuses, including partially completed runs, across monitors and reports.
- Surfaced partially failed run details in report timelines, moved UI status counts onto the machine index, and added a read-only `/query/trends` endpoint for repeated query gaps.

### Added

- Transaction-boundary tests for surfacing index update failures after page writes.
- Run-monitor tests for partial-failure terminal status.
- Run-result policy tests for ingest, lint, and query completion decisions.

## 0.1.0 - 2026-05-25

First public alpha release.

### Added

- Local-first Markdown wiki vault initialization.
- Connector-based ingest for Markdown notes, Hermes sessions, Codex sessions, OpenClaw sessions, and Claude Code sessions.
- Single-file ingest for Markdown and preprocessed documents.
- Optional MinerU-compatible document preprocessing into Markdown.
- Source segmentation for long Markdown and conversation sources.
- Semantic ingest workflow with source normalization, page planning, draft compilation, draft review, quality gate, scoped lint, reports, and checkpoints.
- Lint maintenance workflow with deterministic scan, semantic structural diagnosis, semantic quality diagnosis, maintenance review, operation execution, verification, reports, and ledgers.
- Retrieval-only query workflow for host AI tools, including ranked pages, excerpts, source pointers, graph context, context packs, and optional query reports.
- FastAPI service, CLI commands, local run queue, run monitor, structured logs, vault file locks, and bundled local web console.
- Generic local wiki skill template.
- Public architecture, configuration, CLI, API, concepts, provenance, development, security, and quickstart documentation.
- Scripted release gates for local development checks, release-readiness checks, and clean-clone smoke validation.
- Apache-2.0 license, security policy, and public documentation.

### Notes

- KnoArbor is early alpha. v0.1 workflow API paths and core semantics are intended to remain stable during the v0.1 line, while schemas may still receive additive fields before a later stable release.
- The first release is local-first and single-user. It does not include hosted SaaS deployment, built-in chat answer generation, a built-in vector database, a bundled MinerU runtime, or packaged external workflow templates.
- Runtime wiki data, raw sources, local configs, caches, and private workflow files are intentionally excluded from the repository.
