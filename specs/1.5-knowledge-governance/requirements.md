# 1.5 Knowledge Governance Requirements

## Problem

KnoArbor can already scan and maintain wiki pages, but long-term autonomous
maintenance needs stronger governance: clear risk levels, evidence, before/after
diffs, repeated-issue tracking, quality metrics, and trustworthy repair paths.

The 1.5 line should evolve lint from structural repair into continuous
knowledge governance.

## Goals

- Preserve autonomous safe repairs.
- Keep complex repairs behind semantic review and explicit executor support.
- Track unresolved, deferred, and repeatedly rejected issues.
- Improve before/after reporting for every applied change.
- Expand quality criteria for factuality, completeness, clarity, relevance,
  redundancy, freshness, and source grounding.
- Keep maintenance inspectable through reports and ledgers.

## Non-Goals

- Do not require manual approval for every safe operation.
- Do not allow the model to mutate files directly.
- Do not make lint fetch current web facts by default.
- Do not merge/split/delete pages without explicit executor and verification.

## User Scenarios

### Run Fully Automatic Maintenance

As a user, I can run lint and let safe operations execute without manually
approving each item.

Acceptance criteria:

- Safe operations have deterministic or reviewed support.
- Every write has a report entry, reason, and verification result.
- Failed operations are reported and recoverable.

### Understand A Change

As a user, I can inspect what lint changed and why.

Acceptance criteria:

- Reports show target pages, action names, reasons, before/after diffs, and
  verification outcomes.
- UI can render the same report data without reimplementing lint logic.

### Track Repeated Issues

As a maintainer, I can see whether an issue keeps returning.

Acceptance criteria:

- Lint reports include unresolved/repeated issue signals.
- Repeated rejections are not silently retried forever.

## Current Status

Implemented:

- Deterministic scan and safe fixes.
- Semantic diagnose/review/draft paths.
- Operation verification.
- Lint reports and run records.
- Some before/after operation evidence.

Still in scope for 1.5:

- Strengthen quality governance and repeated issue tracking.
- Make diff/report presentation more complete and consistent.
- Freeze maintenance operation taxonomy and executor boundaries.
