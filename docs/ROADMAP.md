# Roadmap: 1.0.0 to 2.0.0

KnoArbor 1.0.0 establishes the first public local-first release: a working ingest, lint, query, console, API, CLI, and skill integration baseline.

The path to 2.0.0 is about turning that baseline into a stable long-term knowledge system for external users. The core theme is:

> Move from a usable local AI Wiki engine to a dependable, extensible knowledge system with stable installation, stable configuration, stable connectors, stable retrieval, and trustworthy autonomous maintenance.

This roadmap is directional planning. Minor releases may be reordered when implementation evidence suggests a better sequence.

Multi-step roadmap items are implemented through feature specs in
[`specs/`](../specs/README.md). Specs own feature-level requirements, design,
task status, and verification. [Capability Map](CAPABILITY_MAP.md) owns the
cross-feature implementation state. This roadmap owns long-term direction.

## Release Themes

| Version | Theme | Outcome |
| --- | --- | --- |
| 1.1.x | Installation and launch experience | A new user can install, configure, start, and generate the first wiki pages with minimal friction. |
| 1.2.x | Configuration lifecycle | Config files, vault paths, provider settings, and migration become safer and easier to reason about. |
| 1.3.x | Source ecosystem | More input sources become first-class connectors without complicating the ingest pipeline. |
| 1.4.x | Machine index layer | Retrieval becomes more robust through lightweight machine indexes before optional vector search. |
| 1.5.x | Knowledge governance | Lint evolves from structural repair to continuous quality and provenance governance. |
| 1.6.x | Productized console | The local console becomes a mature product surface for non-developer workflows. |
| 1.7.x | CLI, API, and skill closure | Terminal, HTTP, and host-AI workflows expose the same core capabilities with stable contracts. |
| 2.0.0 | Compatibility baseline | Stable connector, config, API, and vault contracts become the long-term compatibility baseline. |

## 1.1.x: Installation And Launch Experience

Goal: make the first ten minutes reliable.

Focus areas:

- Continue improving the npm launcher so Node-first users can discover and start the Python runtime with less friction.
- Keep `uv`/Python installation as the reliable reference path.
- Improve `knoar init`, `knoar doctor`, and `knoar serve` so users know exactly what to do next.
- Provide a short "first wiki page" path using example content.
- Make model-provider setup errors explicit and actionable.
- Keep the default local service entry at `http://127.0.0.1:8000`.

Done when:

- A fresh user can clone, configure one provider, start the console, and create a page without reading architecture docs.
- npm installation either works as a launcher or clearly delegates to the Python runtime without confusion.

## 1.2.x: Configuration Lifecycle

Goal: make configuration stable, migratable, and user-safe.

Focus areas:

- Add explicit config schema versioning.
- Add or strengthen `knoar migrate` for config and vault metadata changes.
- Tighten config validation and error codes.
- Keep secrets in `.env`; never write real keys into `config.yaml`.
- Improve multi-vault configuration without making the default single-vault workflow harder.
- Make UI config edits and CLI config edits share the same validation contract.

Done when:

- Config changes across versions are documented and machine-checkable.
- Users can recover from missing paths, invalid model providers, or old config files without manual code inspection.

## 1.3.x: Source Ecosystem

Goal: expand input coverage without weakening connector boundaries.

Active spec: [1.3 Source Ecosystem](../specs/1.3-source-ecosystem/requirements.md).

Focus areas:

- Continue stabilizing Markdown, Codex, Claude Code, Hermes, OpenClaw, and generic chat connectors.
- Add richer file and web-source workflows behind the same `SourceDocument` contract.
- Keep document preprocessing separate from source ingestion.
- Support folder-level and file-level input selection consistently.
- Make long-source segmentation predictable and visible in reports.
- Avoid source-specific logic inside the semantic agents.

Done when:

- Adding a new source normally means adding a connector and tests, not editing the ingest core.
- Users can understand which source produced which pages and which segments were processed.

## 1.4.x: Machine Index Layer

Goal: make retrieval better without requiring a heavyweight database.

Active spec: [1.4 Machine Index Layer](../specs/1.4-machine-index-layer/requirements.md).

Focus areas:

- Add a machine index layer separate from the human-facing `index.md`.
- Keep page-level BM25 ranking as the default lexical retrieval signal.
- Add SQLite FTS-style retrieval as the first durable local index.
- Keep vector search optional, not required for the default install.
- Track index freshness, rebuild status, and failure states.
- Let ingest and lint use the same index provider contracts.

Done when:

- Query quality improves on medium-sized vaults without requiring vector infrastructure.
- `index.md` remains useful for humans, while machine retrieval uses purpose-built indexes.

## 1.5.x: Knowledge Governance

Goal: make autonomous maintenance trustworthy.

Active spec: [1.5 Knowledge Governance](../specs/1.5-knowledge-governance/requirements.md).

Focus areas:

- Expand lint from deterministic structure checks into quality, duplication, provenance, and freshness governance.
- Preserve the reviewed-operation model for risk-aware autonomous repair.
- Add stronger before/after diff reporting for maintenance operations.
- Track unresolved or repeatedly rejected maintenance issues.
- Improve quality metrics for factuality, completeness, clarity, relevance, redundancy, and source grounding.

Done when:

- Safe repairs can run automatically.
- Complex repairs can be reviewed by the maintenance agent and either applied or deferred with clear evidence.
- Users can understand what changed and why.

## 1.6.x: Productized Console

Goal: make the UI feel like a mature product surface.

Active spec: [1.6 Productized Console](../specs/1.6-productized-console/requirements.md).

Focus areas:

- Improve first-run onboarding.
- Refine source, run, report, graph, wiki, and token-analysis pages.
- Make run reports directly actionable: show written pages, changed pages, diffs, and links.
- Improve loading performance and avoid unnecessary scans on page navigation.
- Consider a mature component system only if it reduces custom UI complexity.

Done when:

- Users can operate the core workflows from the console without understanding every internal report field.
- The UI helps users answer: What is configured? What is running? What changed? What should I do next?

## 1.7.x: CLI, API, And Skill Closure

Goal: make all user-facing surfaces consistent.

Active spec: [1.7 CLI, API, And Skill Closure](../specs/1.7-cli-api-skill-closure/requirements.md).

Focus areas:

- Keep the public API small: health, doctor, ingest, lint, query, runs, and wiki pages.
- Make CLI output human-readable by default and machine-readable with `--json`.
- Keep skill behavior centered on host-AI context retrieval.
- Add skill operations only when they map cleanly to stable API capabilities.
- Preserve API response envelopes and schema versions.

Done when:

- CLI, API, UI, and skill entry points feel like different front doors into the same system.
- External automation can depend on the public API without chasing implementation details.

## 2.0.0: Long-Term Compatibility Baseline

2.0.0 should be the first release where external users can reasonably expect longer compatibility windows.

The 2.0 baseline should freeze:

- public API endpoint families and response envelopes;
- config schema and migration policy;
- vault directory semantics;
- connector interface contracts;
- source document schema;
- report schemas for ingest, lint, query, and runs;
- basic package and launcher behavior;
- privacy and secret-handling rules.

## Later-Horizon Capabilities

These capabilities are useful and belong to a later product horizon:

- multi-user authentication and permissions;
- hosted SaaS deployment;
- mandatory vector database;
- bundled large model weights;
- cloud synchronization;
- collaborative editing;
- turning KnoArbor into a general-purpose chat assistant.

KnoArbor should remain a knowledge engine that other tools can use. Its console
may include bounded wiki chat, but the product should not become a generic
agent platform.

## Guiding Principles

- Prefer stable contracts over feature breadth.
- Keep source connectors narrow and testable.
- Keep semantic agents focused on decisions that require language understanding.
- Keep deterministic validation outside the model.
- Do not hide failures behind broad fallbacks; expose actionable errors and reports.
- Treat the vault as user data and never overwrite it during tests or initialization.
- Make every generated or maintained page traceable to source evidence.
