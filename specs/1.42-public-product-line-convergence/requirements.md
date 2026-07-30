# Public Product Line Convergence Requirements

Status: Accepted

## Ownership

This specification owns the one-time public-safe convergence from the KnoArbor
2.3.1 public baseline to the current reusable platform capabilities, the
product-identity authority shared by Python, Renderer, and Electron, and the
long-term public-upstream/private-downstream delivery rule.

It does not take ownership from the ingest, retrieval, chat, vault, renderer,
desktop, API, CLI, or release specifications. Each migrated capability remains
owned and verified by its domain specification.

## Problem

Reusable platform development continued on the private SieArbor product line
while the public KnoArbor line remained at 2.3.1. Directly merging, rebasing, or
branching from private history would expose private history and would also mix
product-specific identity, update, provider, and release behavior into the
public product.

The public product therefore needs a content-level convergence that preserves a
public-only Git ancestry and makes future reusable development originate in the
public upstream.

## Goals

1. Bring current reusable ingest, storage, retrieval, chat, renderer, desktop,
   validation, and governance capabilities to KnoArbor.
2. Preserve a Git ancestry derived exclusively from the public KnoArbor
   baseline.
3. Establish one canonical product manifest and generated language adapters for
   Python, Renderer, and Electron.
4. Preserve or explicitly migrate supported KnoArbor 2.3.1 configuration,
   vault, API, CLI, and desktop data.
5. Keep company-only branding, providers, update distribution, documentation,
   assets, and release policy outside the public repository.
6. Make KnoArbor the upstream owner of reusable behavior after convergence.

## Non-Goals

1. Reproduce SieArbor commit history, release numbers, branding, or exact tree.
2. Publish the intranet differential update authority or company release
   infrastructure.
3. Maintain two factual authorities, two ingest implementations, or permanent
   compatibility fallbacks.
4. Rename the `knoarbor` Python package, CLI commands, vault runtime directory,
   or public API merely for product-line symmetry.
5. Require partial migration commits to be independently releasable.

## Requirements

### R1 — Public-only ancestry

Every convergence commit must descend from the public KnoArbor baseline. The
private SieArbor branch must not be an ancestor of the candidate public branch.
Transferred content must enter through reviewed patches or public-safe
reimplementation.

### R2 — Explicit transfer classification

Every private-line capability in scope must be classified as `adopt`, `adapt`,
`reject`, or `defer`, with a public owner and verification target. Unclassified
files or commits must not enter the public candidate.

### R3 — Single product identity authority

One versioned product manifest must own product name, identifiers, environment
prefix, default vault label, URLs, desktop data root, renderer assets, and
product capability switches. Python and TypeScript representations must be
generated or validated from that manifest and must not become independent
authorities.

### R4 — No private product leakage

The public tree, generated artifacts, commit messages, documentation, and
release metadata must contain no SieArbor or company-only identity, endpoints,
assets, credentials, provider defaults, or distribution rules.

### R5 — Owner-preserving migration

Persisted facts, active revisions, indexes, projections, chat sessions,
configuration, and desktop data must be migrated by their accepted owners. A
migration may read an old representation, but current runtime behavior must
have exactly one write authority.

### R6 — Public compatibility decision

Every changed public or persisted contract must declare one of: compatible,
automatically migrated, explicitly rejected with a user-facing error, or
release-breaking. Release numbering must follow the resulting compatibility
matrix rather than copy a SieArbor version.

### R7 — Future direction

After convergence, reusable fixes and features must land in KnoArbor first and
flow into the private product line. Private-only work must remain in private
owners or overlays and must not modify reusable owners unless the reusable
change is first accepted upstream.

## Representative Scenarios

1. A maintainer imports transactional ingest code without importing its private
   commit parent, then validates migration from a 2.3.1 vault.
2. A product name change updates the canonical manifest and deterministic
   generation changes the Python, Renderer, and Electron adapters together.
3. An intranet updater is classified `reject`; generic desktop lifecycle fixes
   in adjacent files are reimplemented without the updater.
4. A 2.3.1 configuration cannot be migrated safely; startup reports the exact
   unsupported field and preserves the original file.
5. A future generic retrieval fix lands publicly and is merged downstream into
   the company repository.

## Acceptance Criteria

1. Candidate ancestry contains no private branch head or private-only parent.
2. Transfer manifest has no unclassified in-scope capability.
3. Product identity generation and drift checks pass.
4. Public leakage and secret scans pass on the tree and candidate history.
5. Required historical migration fixtures pass without data loss.
6. Domain owner tests and full-chain acceptance pass on the public candidate.
7. Public source and desktop release artifacts contain only KnoArbor identity.
