# 1.5 Knowledge Governance Design

## Owning Layers

| Layer | Responsibility |
| --- | --- |
| Maintenance | Scan rules, candidates, reviewed operations, execution routing, verification. |
| Semantic | Diagnose/review/draft contracts only. |
| Storage / Writer | Apply approved page changes and preserve atomic write behavior. |
| Report / Audit | Lint reports, operation ledgers, before/after evidence, unresolved issue history. |
| Runtime | Queue state, events, cancellation, failure reporting. |
| UI | Present reports, diffs, and issue status; do not decide maintenance policy. |

## Governance Flow

```text
scan
  -> deterministic safe fixes
  -> semantic candidates
  -> maintenance review
  -> executor routing
  -> deterministic operation apply
  -> draft write apply
  -> provenance refresh apply
  -> graph repair apply
  -> verify
  -> rescan / report / ledger
```

## Executor Boundaries

| Executor | Input | Writes | Automatic Boundary |
| --- | --- | --- | --- |
| Deterministic wiki operation | Approved `deterministic_wiki_operation` candidates | Targeted metadata, wiki links, sections, source fields, redactions | Safe/low-risk operations with complete parameters. |
| Draft write | Approved `draft_write` candidates | Reviewed page drafts or section rewrites | Requires semantic review and writer validation. |
| Provenance refresh | Approved `refresh_request` queue items | Source digest pages and bidirectional source links | Executes when a raw source exists or an existing source digest can be matched through source aliases. |
| Graph repair | Approved safe graph queue items | `Related Pages` links on weakly connected source or knowledge pages | Executes only for weak links or source digests without knowledge links; it does not remove or prune links. |
| Governance queue | Approved audit findings | Reports and ledgers only | Duplicate merge, dense graph pruning, claim review, deletion, and ambiguous source repair. |

## Operation Taxonomy

Operation names should be stable, executor-specific, and narrow. Broad labels
such as "fix page" are not acceptable. Every operation must declare:

- issue/evidence source;
- target page(s);
- action name;
- executor hint;
- risk level;
- confidence;
- expected effect;
- verification rule.

## Automatic Governance Policy

The maintenance layer should reduce routine manual work by executing bounded
repairs after review. Automatic execution is appropriate when:

- the evidence identifies an existing target page;
- the operation changes only metadata, source provenance, or `Related Pages`;
- the executor can produce a before/after diff;
- a rescan can verify that the relevant deterministic issue is reduced.

Operations remain queued when they require semantic content judgment, external
fact checking, page deletion, page merge, dense graph pruning, or ambiguous
source reconstruction.

## Report Contract

Lint reports should be enough for both humans and UI:

- summary metrics;
- deterministic issues;
- semantic candidates;
- review decisions;
- applied operations;
- before/after diffs for modified pages;
- deferred or rejected operations;
- verification results;
- repeated issue signals.

## Rejected Alternatives

### Let The Review Agent Execute Repairs

Rejected because model agents should not own file writes or operation
execution.

### Keep Complex Operations Report-Only Forever

Rejected because the project goal is autonomous governance. Complex operations
may execute once evidence, executor, and verification are explicit.

### Use UI-Only Diff Logic

Rejected because CLI/API/skill users also need to understand maintenance
changes. Diff evidence belongs in reports/audit artifacts.
