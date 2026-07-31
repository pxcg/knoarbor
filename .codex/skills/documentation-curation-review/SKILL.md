---
name: documentation-curation-review
description: Perform a read-only KnoArbor documentation ownership and lifecycle review using source-of-truth, freshness, duplication, indexing, code-anchor, and verification evidence. Use before documentation cleanup, restructuring, migration, archiving, deletion, Direct SDD, or Harness documentation work; editing belongs to the selected delivery lane.
---

# Documentation Curation Review

Read `docs/DOCUMENTATION_GOVERNANCE.md`, `docs/README.md`, the controlling
owner, `specs/registry.json`, and current code/test anchors.

For every document, judge:

- type, audience, unique owner or active parent;
- current/historical status and index membership;
- duplicated truth, mutable task state, stale counts, or migration narration;
- code, schema, command, and verification traceability;
- whether the file lowers or raises discovery cost.

Return `Keep`, `Update`, `Merge`, `Archive`, or `Delete`, with the exact target
owner, links/indexes affected, stable content to preserve, verification, and
deletion condition. Do not edit files, execute Gates, or move all stale
material into Archive to avoid judgment.
