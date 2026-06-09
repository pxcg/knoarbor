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
  -> apply
  -> verify
  -> rescan / report / ledger
```

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
