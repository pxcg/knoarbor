# Development Workflow

This document is the execution entry for KnoArbor development. Classify work
before choosing tools, creating artifacts, or editing code.

## Mutually Exclusive Lanes

| Lane | Use when | Durable output |
| --- | --- | --- |
| Architecture Discovery | The owner, authority, trust boundary, lifecycle, recovery, migration primitive, or product path is still unknown. | A bounded conclusion in the owning spec, contract, or ADR; no speculative implementation. |
| Direct Maintenance | The change preserves observable product/runtime semantics and only maintains tests, fixtures, generated output, documentation, dependencies, or deterministic tooling. | The maintained owner plus focused evidence. |
| Direct SDD | The user result, atomic semantic boundary, formal host, exclusions, negative oracle, and verification path are frozen. One implementation context can change the complete atomic write set. | Updated spec/contract, implementation, focused and affected evidence, independent review, and Git handoff. |
| Patterned Harness | A product request or operational incident retains bounded human authority decisions and coordinated delivery units owned by at least two repository owners under one acceptance boundary. The implementation pattern is already established. | Typed Harness artifacts, Gate receipts, human decisions, delivery record, and compact handoff. |

The lanes do not nest. Risk, file count, or package count alone does not justify
Patterned Harness. A frozen cross-package semantic transaction may remain
Direct SDD. Unknown architecture does not become a Harness Initiative.

## Classification

1. Read the owning stable contract, `specs/registry.json`, and current Git state.
2. State the user outcome, exclusions, exact owner, authority object, affected
   consumers, negative oracle, and rollback boundary.
3. Choose one lane. Record why the adjacent lanes do not apply.
4. Treat changes to Harness Core, Controller, Adapter, Gates, method state, or
   bootstrap as Bootstrap Maintenance: the runtime under replacement cannot
   certify itself.

## Direct Maintenance

Freeze the bounded file set, preserve unrelated work, run the owner-local
checks, run documentation governance when applicable, and close with exact Git
state. Escalate to Direct SDD when product/runtime behavior changes.

## Direct SDD

1. Update or create the smallest valid spec before implementation.
2. Freeze the complete atomic write set and public consumer chain.
3. Implement at the formal host; remove superseded paths.
4. Run focused tests, then one affected/integration closure.
5. Obtain a read-only review in this order:
   `belongs -> authority -> contract -> behavior`.
6. Update long-term docs only for delivered stable facts.
7. Commit one coherent boundary and return a structured handoff.

## Patterned Harness Admission

Admission requires all of the following:

- product request or operational incident provenance;
- exact Git base and request digest;
- one independently reversible Initiative;
- at least two distinct repository owners with exact delivery units;
- one common acceptance boundary;
- bounded human authority decisions;
- established owner, host, lifecycle, recovery, product path, and verification
  pattern;
- an unresolved capability delta;
- an explicit explanation of why Direct SDD is insufficient.

Run it through `pnpm harness --`. The shared Core owns lifecycle, typed
artifacts, role relay, review separation, rollback, Gate receipts, metrics, and
closure. The KnoArbor Adapter owns project paths, Skills, owner resolution,
capability/semantic-host projections, Gates, and branch policy.

## Review, Handoff, And Acceptance

Every lane closes with:

- lane, goal, exclusions, formal host, and owning contract;
- changed and retired paths;
- commands actually run and observed results;
- negative oracle and review verdict;
- exact branch, base, HEAD, and worktree state;
- controlled transitions, remaining blockers, and next valid entry;
- judgments that must not be reopened without new evidence.

Acceptance asks both whether behavior works and whether it works through the
correct authority, surface, and contract.
