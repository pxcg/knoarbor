# Public Product Line Convergence Tasks

Status: In Progress

## Phase 0 — Public Baseline And Governance

- [x] Create an isolated integration branch from public `main@18fde631`.
- [x] Verify the private SieArbor head is not an ancestor.
- [x] Establish the public spec registry and convergence owner.
- [x] Record the public-upstream/private-downstream ADR.
- [x] Add the classified transfer manifest.
- [ ] Bootstrap the generic Initiative Harness for subsequent strict slices.

## Phase 1 — Product Identity Boundary

- [x] Add the canonical KnoArbor product manifest and schema validation.
- [x] Generate or validate Python, Renderer, and Electron product adapters.
- [x] Route environment variables, desktop identifiers, data roots, URLs, and
  capability switches through the product authority.
- [x] Add product drift and public leakage tests.
- [ ] Remove duplicate identity constants and undocumented overrides.

## Phase 2 — Factual Ingest And Storage

- [ ] Reconcile the accepted Raw-grounded ingest specifications and ADRs.
- [ ] Port immutable factual revisions and active-head storage.
- [ ] Port transactional ingest coordination, execution, recovery, and
  deterministic materialization.
- [ ] Implement and verify 2.3.1 config/vault migration outcomes.
- [ ] Delete superseded write authorities after migration coverage passes.

## Phase 3 — Query, Chat, And Editing

- [ ] Port active-Raw and graph retrieval with one evidence owner.
- [ ] Port typed query outcomes, snapshots, and exact support spans.
- [ ] Port Chat retrieval, answer-decision, composition, and citation contracts.
- [ ] Port Raw and projection revision editing with stale-parent protection.
- [ ] Remove superseded page-authority and chat fallback paths.

## Phase 4 — Renderer And Desktop

- [ ] Port reusable renderer domain organization and vault-scoped workflows.
- [ ] Port citation, Raw, Markdown, image, and editing interactions.
- [ ] Port generic desktop persistence, lifecycle, backup, and packaging fixes.
- [ ] Reject intranet updater and private product/release behavior.
- [ ] Validate macOS and Windows public artifact identity and data preservation.

## Phase 5 — Release Closure

- [ ] Complete the compatibility matrix and release-version decision.
- [ ] Align public contracts, architecture, user docs, and release notes.
- [ ] Pass focused, dependency-closure, clean-clone, packaging, leakage, and
  full-chain acceptance gates.
- [ ] Audit candidate ancestry and changed history.
- [ ] Reconcile the accepted public release downstream without changing public
  history.
- [ ] Mark this specification Implemented only after delivery evidence closes.
