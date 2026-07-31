---
name: semantic-contract-review
description: Independently review a frozen KnoArbor Direct SDD contract, Harness design, or implementation for formal host, authority, typed contract, lifecycle, recovery, migration, fallback, security, and consumer consistency. Use for read-only design or diff review after producer evidence exists; do not repair findings or repeat deterministic Gates.
---

# Semantic Contract Review

Bind the request, lane, exclusions, owning contract, formal host, authority
chain, exact write set/diff, negative oracle, and producer evidence. In Harness
mode also bind Admission, Requirement, Design, TaskPlan, RoleTask, Gate
receipts, and implementation report.

Review in this order:

1. `belongs`: behavior resides at its sole formal host.
2. `authority`: canonical truth, lifecycle, recovery, coordination, and
   publication are not duplicated or inferred by consumers.
3. `contract`: public/typed surfaces are singular, required authority is not
   optional, transitions have owners and retirement oracles, and fallbacks do
   not merge truth.
4. `behavior`: focused evidence covers success, failure, cancellation,
   recovery, and affected consumers.

Return one complete ordered finding batch, claim coverage, invalidated frozen
inputs, responsible workflow entry, and a read-only verdict. Route unknown
owners or primitives to Architecture Discovery. Do not mutate files or invent
stronger requirements than the accepted contract.
