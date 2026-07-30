# Capability Map

This document tracks KnoArbor's stable capability boundaries and current
implementation state. It complements the roadmap and feature specs:

- `docs/ROADMAP.md` owns long-term release direction.
- `specs/<feature>/` owns feature-level requirements, design, tasks, and
  verification.
- this file owns the cross-feature capability state.

## Status Legend

| Status | Meaning |
| --- | --- |
| Frozen | The boundary is accepted; later work extends through this boundary. |
| Implemented | The capability has a working baseline and tests or release checks. |
| Partial | The main direction is accepted; implementation or verification is still incomplete. |
| Planned | The capability is accepted for a future roadmap line. |
| Deferred | The capability is useful, with a later product horizon. |

## Core Capabilities

| Capability | Status | Current boundary | Owning docs/specs |
| --- | --- | --- | --- |
| Source connectors | Implemented | Connectors convert external material into `SourceDocument`; source-specific parsing stays in connector or document-processing code. | [1.3 Source Ecosystem](../specs/1.3-source-ecosystem/requirements.md), [Configuration](CONFIGURATION.md) |
| Source catalog | Implemented | `/sources`, `knoar sources --catalog`, and the console expose connector metadata, settings schema, and runtime configuration state. | [1.3 Source Ecosystem](../specs/1.3-source-ecosystem/requirements.md), [API](API.md), [CLI](CLI.md) |
| Document preprocessing | Partial | Rich documents are prepared into Markdown before shared ingest; MinerU-compatible services are an adapter behind document processing. | [Architecture](ARCHITECTURE.md), [Configuration](CONFIGURATION.md) |
| Source segmentation | Implemented | Long sources are segmented after normalization and checkpoint windowing, then aggregated at source/window level before commit. | [Architecture](ARCHITECTURE.md), [1.3 Source Ecosystem](../specs/1.3-source-ecosystem/requirements.md) |
| Ingest pipeline | Implemented | Ingest freezes normalized inputs, creates source units and immutable factual revisions, publishes active heads atomically, then materializes rebuildable wiki/index projections and reports. | [Architecture](ARCHITECTURE.md), [Concepts](CONCEPTS.md) |
| Lint governance | Implemented | Lint owns deterministic scans, semantic candidates, reviewed operation execution, verification, and maintenance reports. | [1.5 Knowledge Governance](../specs/1.5-knowledge-governance/requirements.md), [Architecture](ARCHITECTURE.md) |
| Query context retrieval | Implemented | Query ranks active knowledge atoms, selects answer-bearing claims, follows explicit evidence edges to complete active raw source units, and returns stable evidence identities, gaps, trace data, and optional projection locators without scoring raw text or treating pages as factual authority. | [1.38 Semantic Indexed Raw Query](../specs/1.38-semantic-indexed-raw-query/requirements.md), [API](API.md) |
| Runtime execution and monitor | Implemented | Runtime owns persisted transactional task state, in-process scheduling, heartbeats, cancellation, recovery metadata, and active/recent run views; it does not depend on a separate persistent worker queue. | [Architecture](ARCHITECTURE.md), [API](API.md) |
| Report and audit layer | Implemented | Audit owns ingest, lint, query, token, and failure reports plus machine-readable ledgers. | [Architecture](ARCHITECTURE.md), [Testing](TESTING.md) |
| Model gateway | Implemented | Model calls pass through provider adapters, OpenAI-compatible or Ollama-native transport, structured-output handling, usage metrics, and endpoint checks. | [Architecture](ARCHITECTURE.md), [Configuration](CONFIGURATION.md) |
| Multi-vault configuration | Implemented | Config supports named vaults and active vault selection; public APIs accept vault selection parameters where relevant. | [Configuration](CONFIGURATION.md), [API](API.md) |
| Web console | Partial | The console provides local product workflows for sources, ingest, lint, query, wiki browsing, graph, reports, runs, settings, and token analysis. | [1.6 Productized Console](../specs/1.6-productized-console/requirements.md), [Showcase](SHOWCASE.md) |
| Frontend i18n guardrails | Implemented | UI copy is centralized under `renderer/src/i18n/`; the frontend build checks Chinese/English key parity before bundling. | [Testing](TESTING.md) |
| CLI surface | Implemented | CLI commands provide human-readable output and JSON output for automation. | [1.7 CLI/API/Skill Closure](../specs/1.7-cli-api-skill-closure/requirements.md), [CLI](CLI.md) |
| Public API surface | Implemented | Public endpoint families cover health/doctor, vaults/config/models, sources, ingest/lint/query, chat, runs/reports, wiki pages, tokens, and runtime metadata through stable domain contracts. | [API](API.md), [API Compatibility](API_COMPATIBILITY.md) |
| Host-AI skill | Implemented | The skill calls local APIs for query, page reading, source catalog, runs, reports, ingest, and lint operations. | [1.7 CLI/API/Skill Closure](../specs/1.7-cli-api-skill-closure/requirements.md) |
| Machine index layer | Partial | Immutable index generations selected by `.knoarbor/index/CURRENT` support page and graph navigation. Default query reads active semantic atoms and explicit claim-evidence edges from factual storage; richer provider choices and freshness diagnostics remain incomplete. | [1.4 Machine Index Layer](../specs/1.4-machine-index-layer/requirements.md), [1.38 Semantic Indexed Raw Query](../specs/1.38-semantic-indexed-raw-query/requirements.md) |
| Optional vector retrieval | Deferred | Vector retrieval remains an optional provider behind the index contract. | [1.4 Machine Index Layer](../specs/1.4-machine-index-layer/requirements.md) |
| Hosted multi-user service | Deferred | Local-first single-user usage remains the active product baseline. | [Roadmap](ROADMAP.md) |

## Capability Completion Rule

A capability reaches `Implemented` when these conditions hold:

- a public or internal contract is documented;
- the owning layer is named in architecture or a feature spec;
- automated tests or release gates cover the core path;
- user-visible behavior appears in public docs when the capability is public;
- reports, ledgers, or traces expose enough evidence for later diagnosis when
  the capability mutates the vault or calls a model.

`Frozen` is a boundary state, separate from feature completion. A frozen
boundary can contain planned or partial capabilities.
