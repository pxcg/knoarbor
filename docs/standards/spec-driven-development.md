# Spec-Driven Development

KnoArbor uses specs to freeze material behavior and architecture before
implementation. `specs/README.md` and `specs/registry.json` are the registry
authorities; this document defines how specs participate in each workflow lane.

## Spec Levels

- **No dedicated spec:** bounded Direct Maintenance with no durable behavior,
  architecture, public contract, or verification-policy change.
- **Lightweight revision:** a frozen Direct SDD change owned by an existing
  spec. Update only the files whose accepted contract changes.
- **Full spec:** new or material changes to architecture, public or semantic
  contracts, persistence, lifecycle/recovery, cross-layer behavior, autonomous
  maintenance, packaging, release, or development control.

Full specs contain `requirements.md`, `design.md`, `tasks.md`, and
`verification.md`. Requirements define outcomes and exclusions; Design freezes
owners, authority, contracts, lifecycle, recovery, migration and rollback;
Tasks own implementation status; Verification owns executable oracles.

## External Reference Reuse

When adapting another repository, article, or framework, add a bounded reuse
manifest to the owning spec. Classify each candidate mechanism:

- `adopt`: use unchanged;
- `adapt`: reuse with named project-specific differences;
- `reject`: intentionally do not introduce;
- `defer`: useful but not justified by current evidence.

Each entry names the source, target owner, verification, cleanup/retirement
condition, and whether it changes current product authority. Reference
material never becomes a parallel source of truth.

## Lane Integration

- Architecture Discovery may update a spec only with evidence-backed
  conclusions; it does not mark implementation complete.
- Direct SDD updates the existing owner before code and keeps its task and
  verification state aligned.
- Patterned Harness consumes accepted feature specs and returns only delivered
  long-term deltas. Mutable RoleTask, Gate, decision, and stage state remains in
  Harness/Git.
- Bootstrap Maintenance may revise the Harness owner without self-hosting.

## Completion

A spec is Implemented only when required tasks are complete, verification
commands have current evidence, stable docs reflect the delivered system, and
the registry lifecycle agrees. Historical process narration belongs in Git or
an independently valuable evidence record, not in current contracts.
