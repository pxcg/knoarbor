# 1.5 Knowledge Governance Tasks

## Operation Taxonomy

- [done] Audit existing lint operation names and executor hints.
- [done] Document frozen operation categories in this spec.
- [later] Add tests that reject unknown or unsupported operation names.

## Evidence And Review

- [next] Ensure every reviewed decision records evidence, confidence, risk,
  expected effect, and executor fit.
- [later] Add repeated rejection tracking.
- [later] Add unresolved issue carryover summary.

## Reports And Diffs

- [done] Ensure applied operations include before/after diff evidence.
- [later] Normalize report data for UI rendering without parsing prose.
- [later] Add report schema examples to docs once stable.

## Automatic Governance Executors

- [done] Execute approved provenance refresh requests when raw sources or
  matching source digest aliases exist.
- [done] Execute approved safe graph repairs for weak links and source digests
  without knowledge links.
- [later] Add explicit duplicate merge executor only when merge evidence and
  archive policy are fully specified.
- [later] Add dense graph pruning only after a stable pruning policy exists.

## Quality Governance

- [later] Expand quality metrics and scoring boundaries.
- [later] Add freshness candidate policy.
- [later] Add duplicate/merge governance when executor support is explicit.

## Deferred

- [deferred] Fully automatic page deletion.
- [deferred] Mandatory external web fact checking.
- [deferred] Multi-user approval workflow.
