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
| Ingest pipeline | Implemented | Ingest owns source normalization, segment-level semantic processing, write policy, scoped lint, checkpoint commit, and report output. | [Architecture](ARCHITECTURE.md), [Concepts](CONCEPTS.md) |
| Lint governance | Implemented | Lint owns deterministic scans, semantic candidates, reviewed operation execution, verification, and maintenance reports. | [1.5 Knowledge Governance](../specs/1.5-knowledge-governance/requirements.md), [Architecture](ARCHITECTURE.md) |
| Query context retrieval | Implemented | Query returns field-weighted BM25 ranked wiki pages, page roles (`primary`, `supporting`, `source`), answer scope, answer set, coverage signals, excerpts, source pointers, trace data, graph relevance signals, and context packs for host AI tools. | [1.7 CLI/API/Skill Closure](../specs/1.7-cli-api-skill-closure/requirements.md), [API](API.md) |
| Runtime queue and monitor | Implemented | Runtime owns queued execution, run state, heartbeats, cancellation, recovery metadata, and active/recent run views. | [Architecture](ARCHITECTURE.md), [API](API.md) |
| Report and audit layer | Implemented | Audit owns ingest, lint, query, token, and failure reports plus machine-readable ledgers. | [Architecture](ARCHITECTURE.md), [Testing](TESTING.md) |
| Model gateway | Implemented | Model calls pass through provider adapters, OpenAI-compatible transport, structured-output handling, usage metrics, and endpoint checks. | [Architecture](ARCHITECTURE.md), [Configuration](CONFIGURATION.md) |
| Multi-vault configuration | Implemented | Config supports named vaults and active vault selection; public APIs accept vault selection parameters where relevant. | [Configuration](CONFIGURATION.md), [API](API.md) |
| Web console | Partial | The console provides local product workflows for sources, ingest, lint, query, wiki browsing, graph, reports, runs, settings, and token analysis. | [1.6 Productized Console](../specs/1.6-productized-console/requirements.md), [Showcase](SHOWCASE.md) |
| Frontend i18n guardrails | Implemented | UI copy is centralized under `web/src/i18n/`; the frontend build checks Chinese/English key parity before bundling. | [Testing](TESTING.md) |
| CLI surface | Implemented | CLI commands provide human-readable output and JSON output for automation. | [1.7 CLI/API/Skill Closure](../specs/1.7-cli-api-skill-closure/requirements.md), [CLI](CLI.md) |
| Public API surface | Implemented | Public endpoint families stay small: health, doctor, sources, ingest, lint, query, runs, reports, wiki pages, and runtime metadata. | [API](API.md), [API Compatibility](API_COMPATIBILITY.md) |
| Host-AI skill | Implemented | The skill calls local APIs for query, page reading, source catalog, runs, reports, ingest, and lint operations. | [1.7 CLI/API/Skill Closure](../specs/1.7-cli-api-skill-closure/requirements.md) |
| Machine index layer | Partial | Retrieval already uses an index provider boundary and page-level BM25 scoring. Durable local index artifacts, rebuild state, and freshness diagnostics remain planned. | [1.4 Machine Index Layer](../specs/1.4-machine-index-layer/requirements.md) |
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
