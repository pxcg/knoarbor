# Public Product Line Convergence Design

Status: Accepted

## Decision Summary

KnoArbor remains the public upstream. Convergence starts from public
`main@18fde631` in an isolated worktree and transfers reviewed content without
private Git ancestry. Reusable capabilities retain their domain owners.
Product-specific values move behind one canonical manifest with deterministic
adapters for Python, Renderer, Electron, packaging, and validation.

ADR 0022 owns the durable public-upstream/private-downstream direction.

## Baselines

| Role | Commit | Meaning |
| --- | --- | --- |
| Public parent | `18fde631` | KnoArbor 2.3.1 public release baseline |
| Reviewed capability source | `53da106c` | Current private-line behavior snapshot |
| Private release marker | `72985cbf` | SieArbor 2.5.3 tag target; not the complete source snapshot |

Source commit identifiers are review locators, not public ancestors.

## End-to-End Control Flow

```text
public main
  -> isolated public integration branch
  -> product-boundary and governance bootstrap
  -> classified owner-by-owner content transfer
  -> persisted-contract migration and focused owner validation
  -> renderer/desktop consumer validation
  -> public leakage and ancestry audit
  -> full-chain acceptance
  -> public release
  -> downstream private reconciliation
```

## Ownership And Handoffs

| Concern | Authority | Derived consumers |
| --- | --- | --- |
| Transfer status | `transfer-manifest.json` under this spec | Review summaries and release checklist |
| Product values | canonical product manifest | Python, Renderer, Electron, packaging adapters |
| Spec lifecycle | `specs/registry.json` | Specs index and governance checks |
| Facts and active revisions | ingest/storage owners after their migration | Wiki projections, indexes, query, chat |
| Public compatibility | owning public contract plus compatibility matrix | Release version and migration UX |
| Private overlay | private repository only | Private builds and releases |

The transfer manifest records paths and capability slices, but does not become
a second product-task tracker. `tasks.md` owns implementation completion.

## Product Manifest Contract

The manifest is versioned and contains only JSON-compatible values:

```text
schema_version
product.name
product.service_title
product.default_vault_name
environment.prefix
desktop.app_id
desktop.app_user_model_id
desktop.data_dir
renderer.logo_path
links.help
capabilities.public_help
capabilities.desktop_updates
```

A deterministic generator validates the schema, rejects unknown or missing
fields, and writes language adapters with a source digest. Checked-in generated
adapters are allowed for packaging, but drift is a hard validation failure.
Runtime environment overrides may change values explicitly allowed by the
adapter; they do not change the manifest authority or invent another prefix.

Private manifests and private assets are never committed publicly.

## Transfer Model

Each transfer slice has:

- classification: `adopt`, `adapt`, `reject`, or `defer`;
- source locator;
- public owning spec or contract;
- included and excluded paths;
- migration responsibility;
- focused and consumer validation;
- cleanup target for superseded public paths.

Transfer uses reviewed patches, manual root-cause reimplementation, or
allowlisted snapshot extraction. It never uses a merge, rebase, graft, replace
reference, or branch parent from the private line.

## Ordered Dependency Slices

1. Governance, product identity, and transfer classification.
2. Factual schemas, immutable storage, transactional ingest, and migration.
3. Deterministic materialization and machine indexes.
4. Active-Raw query and evidence resolution.
5. Chat decision, composition, citations, and edit lifecycles.
6. Renderer domain organization and user workflows.
7. Generic desktop lifecycle, persistence, and public packaging.
8. Public docs, release metadata, full-chain acceptance, and downstream
   reconciliation.

Later slices may be developed on the integration branch before earlier slices
are released, but they cannot validate against a temporary second authority.

## Compatibility Matrix

Every affected contract is assigned one outcome:

| Outcome | Required behavior |
| --- | --- |
| Compatible | Existing data and callers work unchanged |
| Migrated | Deterministic, idempotent migration preserves the original until success |
| Rejected | Explicit typed/user-facing error identifies recovery action |
| Breaking | Public release notes and version communicate removal |

At minimum the matrix covers config schema, vault layout, factual storage,
indexes, run state, chat sessions, API payloads, CLI flags, desktop data root,
and packaged artifacts.

## Failure, Recovery, And Idempotency

- A failed transfer slice leaves Git history recoverable and does not mutate
  user data.
- Persisted migrations write new state before switching authority and retain
  enough information to retry or report a precise rejection.
- Derived projections and indexes rebuild from the accepted factual authority.
- Transfer and generation commands are deterministic and safe to rerun.
- Private downstream reconciliation occurs only after public acceptance and
  preserves private product state through an explicit reviewed merge.

## Security And Privacy

Public release preparation scans both changed content and reachable candidate
history for private names, endpoints, assets, credentials, and internal
distribution metadata. Binary assets require explicit provenance review.
Candidate commits contain no private parent even when their content was
reimplemented from a reviewed private source.

## Governance Bootstrap

The 2.3.1 public baseline predates the Initiative Harness. The first convergence
slice establishes the registry, this accepted spec, the durable ADR, and the
generic harness before subsequent strict implementation runs. This bootstrap is
bounded to governance and product identity and is reviewed directly through
the spec and Git baseline.

## Rejected Alternatives

### Merge Or Rebase The Private Branch

Rejected because reachable history would disclose private content and make
future public/private separation unreliable.

### De-brand A Branch Created From SieArbor

Rejected because final tree cleanliness does not remove private ancestors or
historical blobs.

### Cherry-pick Every Apparently Generic Commit

Rejected because 167 non-equivalent patches contain cross-cutting private and
generic changes, while the public line also has independent commits that need
semantic reconciliation.

### Permanent Dual Product Branch Development

Rejected because it recreates the same drift. Product overlays may differ;
reusable owners must have one upstream.

### One Monolithic Snapshot Commit

Rejected as the default because it obscures ownership, migration, and focused
review. A snapshot may be used within an allowlisted slice only when the slice
still has explicit owner-level validation.
