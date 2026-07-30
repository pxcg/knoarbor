# ADR 0022: Public Upstream And Private Product Downstream

Status: Accepted

## Context

KnoArbor and SieArbor share an original codebase, but reusable platform work
continued primarily in the private product line while the public line remained
at 2.3.1. Direct reverse integration would make private history and product
material reachable from a public branch. Continuing independent development
would repeatedly recreate a large and difficult-to-audit divergence.

## Decision

KnoArbor is the upstream authority for reusable source, ingest, storage,
retrieval, chat, renderer, desktop-runtime, public-contract, and validation
behavior.

SieArbor is a private downstream product. It may own private branding, product
identity values, providers, update distribution, deployment, compliance, and
company documentation. Reusable changes are accepted in KnoArbor first and then
integrated downstream.

The one-time convergence begins from public history and transfers reviewed
content without making a private commit an ancestor of the public candidate.
Product differences are expressed through explicit product manifests or
private owner modules, not long-lived edits to reusable owners.

## Consequences

- Public history remains auditable and free of private ancestors.
- Reusable fixes have one upstream owner and one primary validation path.
- The first convergence requires content-level review and may temporarily cost
  more than a merge.
- Private work that discovers a reusable defect must upstream the generic root
  fix before or alongside the private integration.
- Downstream reconciliation may require one explicit reviewed merge after
  public parity, but it never changes public ancestry.

## Alternatives

### Continue Two Independent Product Branches

Rejected because generic behavior would continue to diverge and every future
backport would repeat the same classification and compatibility work.

### Merge The Private Branch Into Public

Rejected because deleting private files in the merge result does not remove
private commits or blobs from reachable history.

### Keep A Private Shared Core Only

Rejected because it makes the public project a downstream consumer of a
non-public authority and prevents public contributors from owning reusable
behavior.

## Verification

- Public candidate ancestry excludes the private branch head.
- Transfer records classify private-line capabilities.
- Public leakage scans cover the tree, reachable new history, and release
  artifacts.
- Future reusable changes demonstrate public-first integration.
