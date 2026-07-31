# Capability Map

This document tracks KnoArbor's stable capability boundaries and current
implementation state. It complements the roadmap and feature specs:

- `docs/ROADMAP.md` owns long-term release direction.
- `specs/<feature>/` owns feature-level requirements, design, tasks, and
  verification.
- this file owns the cross-feature capability state.

## Maturity Dimensions

Each capability has one stable ID and four independent maturity dimensions:

- contract: `frozen`, `defined`, or `undefined`;
- implementation: `complete`, `foundation`, `partial`, or `unimplemented`;
- automated evidence: `broad`, `focused`, `mapped`, or `none`;
- product acceptance: `scoped_pass`, `partial`, `pending`, or
  `not_applicable`.

These values are consumed mechanically by the Development Harness Adapter.

## Core Capabilities

| ID | Capability | Contract | Implementation | Automated evidence | Product acceptance | Current boundary | Active owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CAP-SOURCE-CONNECTORS | Source connectors | frozen | complete | broad | scoped_pass | Connectors normalize external material into `SourceDocument`; source-specific parsing stays in connector or document-processing code. | `specs/1.3-source-ecosystem/requirements.md` |
| CAP-SOURCE-CATALOG | Source catalog | defined | complete | focused | scoped_pass | API, CLI, and console expose connector metadata, settings schema, and runtime configuration state. | `specs/1.3-source-ecosystem/requirements.md` |
| CAP-DOCUMENT-PREPROCESSING | Document preprocessing | defined | partial | focused | partial | Rich documents are prepared into Markdown behind the shared document-processing boundary. | `docs/ARCHITECTURE.md` |
| CAP-SOURCE-SEGMENTATION | Source segmentation | frozen | complete | focused | scoped_pass | Segmentation follows normalization and checkpoint windowing before source/window aggregation. | `specs/1.3-source-ecosystem/requirements.md` |
| CAP-INGEST | Ingest pipeline | frozen | complete | broad | scoped_pass | Ingest freezes inputs, creates source units and factual revisions, atomically publishes active heads, and materializes rebuildable projections. | `specs/1.26-raw-grounded-ingest-chain/requirements.md` |
| CAP-LINT | Lint governance | defined | complete | focused | scoped_pass | Lint owns deterministic scans, semantic candidates, reviewed operation execution, verification, and reports. | `specs/1.5-knowledge-governance/requirements.md` |
| CAP-QUERY | Query context retrieval | frozen | complete | broad | scoped_pass | Query selects claims and resolves complete active Raw evidence without treating projections as factual authority. | `specs/1.38-semantic-indexed-raw-query/requirements.md` |
| CAP-RUNTIME | Runtime execution and monitor | frozen | complete | broad | scoped_pass | Runtime owns transactional task state, scheduling, heartbeats, cancellation, recovery, and run views. | `docs/ARCHITECTURE.md` |
| CAP-AUDIT | Report and audit layer | defined | complete | focused | scoped_pass | Audit owns ingest, lint, query, token, and failure reports plus machine-readable ledgers. | `docs/REPORT_CONTRACT.md` |
| CAP-MODEL-GATEWAY | Model gateway | defined | complete | focused | scoped_pass | Provider adapters own transport, structured output, usage metrics, and endpoint checks. | `docs/CONTRACTS.md` |
| CAP-MULTI-VAULT | Multi-vault configuration | defined | complete | focused | scoped_pass | Named vaults and active selection flow through public API/config contracts. | `specs/1.9-vault-workspaces/requirements.md` |
| CAP-WEB-CONSOLE | Web console | defined | partial | focused | partial | The console exposes local product workflows through typed API consumers. | `specs/1.6-productized-console/requirements.md` |
| CAP-I18N | Frontend i18n guardrails | defined | complete | focused | scoped_pass | Renderer copy uses centralized Chinese/English keys with deterministic parity checks. | `docs/UI_CONTRACT.md` |
| CAP-CLI | CLI surface | frozen | complete | broad | scoped_pass | CLI commands provide human and JSON output through stable domain contracts. | `docs/CLI.md` |
| CAP-PUBLIC-API | Public API surface | frozen | complete | broad | scoped_pass | Stable endpoint families publish domain contracts for product adapters. | `docs/API.md` |
| CAP-HOST-SKILL | Host-AI skill | defined | complete | focused | scoped_pass | The skill calls stable local APIs and does not own product truth. | `specs/1.7-cli-api-skill-closure/requirements.md` |
| CAP-MACHINE-INDEX | Machine index layer | defined | partial | focused | partial | Immutable index generations support navigation while factual storage remains authority. | `specs/1.4-machine-index-layer/requirements.md` |
| CAP-VECTOR-RETRIEVAL | Optional vector retrieval | defined | unimplemented | mapped | pending | Vector retrieval remains optional behind the index provider contract. | `specs/1.4-machine-index-layer/requirements.md` |
| CAP-HOSTED-SERVICE | Hosted multi-user service | undefined | unimplemented | none | not_applicable | Local-first single-user use remains the active baseline. | `docs/ROADMAP.md` |
| CAP-DEVELOPMENT-HARNESS | Development Harness | frozen | complete | broad | partial | Shared Core plus the KnoArbor Adapter provides Patterned Harness while direct lanes remain valid. | `specs/1.41-project-development-harness/requirements.md` |

## Capability Completion Rule

A capability reaches `complete` implementation and `scoped_pass` acceptance
when these conditions hold:

- a public or internal contract is documented;
- the owning layer is named in architecture or a feature spec;
- automated tests or release gates cover the core path;
- user-visible behavior appears in public docs when the capability is public;
- reports, ledgers, or traces expose enough evidence for later diagnosis when
  the capability mutates the vault or calls a model.

Contract maturity is separate from feature completion. A frozen contract can
still have partial implementation or acceptance.
