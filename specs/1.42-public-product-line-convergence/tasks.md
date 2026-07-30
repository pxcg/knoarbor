# Public Product Line Convergence Tasks

Status: Implemented

## Phase 0 — Public Baseline And Governance

- [x] Create an isolated integration branch from public `main@18fde631`.
- [x] Verify the private SieArbor head is not an ancestor.
- [x] Establish the public spec registry and convergence owner.
- [x] Record the public-upstream/private-downstream ADR.
- [x] Add the classified transfer manifest.
- [x] Retain the generic Initiative Harness as an optional maintainer utility.
- [x] Record ordinary SDD, Git, and verification closure as the convergence
  delivery process.

## Phase 1 — Product Identity Boundary

- [x] Add the canonical KnoArbor product manifest and schema validation.
- [x] Generate or validate Python, Renderer, and Electron product adapters.
- [x] Route environment variables, desktop identifiers, data roots, URLs, and
  capability switches through the product authority.
- [x] Add product drift and public leakage tests.
- [x] Remove duplicate identity constants and undocumented overrides.

## Phase 2 — Factual Ingest And Storage

- [x] Reconcile the accepted Raw-grounded ingest specifications and ADRs.
- [x] Port immutable factual revisions and active-head storage.
- [x] Port transactional ingest coordination, execution, recovery, and
  deterministic materialization.
- [x] Implement and verify 2.3.1 config/vault migration outcomes.
- [x] Delete superseded write authorities after migration coverage passes.

## Phase 3 — Query, Chat, And Editing

- [x] Port active-Raw and graph retrieval with one evidence owner.
- [x] Port typed query outcomes, snapshots, and exact support spans.
- [x] Port Chat retrieval, answer-decision, composition, and citation contracts.
- [x] Port Raw and projection revision editing with stale-parent protection.
- [x] Remove superseded page-authority and chat fallback paths.

## Phase 4 — Renderer And Desktop

- [x] Port reusable renderer domain organization and vault-scoped workflows.
- [x] Port citation, Raw, Markdown, image, and editing interactions.
- [x] Port generic desktop persistence, lifecycle, backup, and packaging fixes.
- [x] Reject intranet updater and private product/release behavior.
- [x] Validate the macOS public artifact and Windows packaging contracts; reject
  non-native Windows builds that would contain a foreign service binary.

## Phase 5 — Release Closure

- [x] Complete the compatibility matrix and release-version decision.
- [x] Align public contracts, architecture, user docs, and release notes.
- [x] Pass focused, dependency-closure, clean-clone, packaging, leakage, and
  full-chain acceptance gates.
- [x] Audit candidate ancestry and changed history.
- [x] Produce a public-only handoff branch; downstream private reconciliation
  remains a separate repository operation after public review.
- [x] Mark this specification Implemented only after delivery evidence closes.
