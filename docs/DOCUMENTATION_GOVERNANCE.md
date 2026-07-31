# Documentation Governance

This is the sole standard for KnoArbor document classes, sources of truth,
required structure, lifecycle, and cleanup. `docs/README.md` is navigation only.

## Purpose

Tracked documentation retains:

1. current product, architecture, capability, operation, and verification
   contracts;
2. stable local detail still needed to understand those contracts;
3. history with independent decision or audit value.

Task plans, RoleTasks, stage state, Gate output, progress logs, and ordinary
handoffs remain in Harness/Git.

## Classes And Owners

| Class | Owner | Sole responsibility |
| --- | --- | --- |
| User guides | `QUICKSTART.md`, `INSTALLATION.md`, `CONFIGURATION.md`, `TROUBLESHOOTING.md`, `BACKUP_AND_RECOVERY.md`, `CONCEPTS.md` | First use, normal operation, recovery, and stable concepts |
| Product tour | root `README.md`, `SHOWCASE.md` | Product position and demonstrable outcomes |
| Public reference | `API.md`, `CLI.md`, `ERROR_CODES.md` | Stable route, command, and error lookup |
| Active contracts | `CONTRACTS.md`, `API_COMPATIBILITY.md`, `UI_CONTRACT.md`, `REPORT_CONTRACT.md`, `PROVENANCE_DESIGN.md` | Current public/runtime authority and typed boundaries |
| Architecture/product | `ARCHITECTURE.md`, `CAPABILITY_MAP.md`, `ROADMAP.md`, `adr/` | Layers, formal hosts, capability maturity, direction, and durable decisions |
| Engineering standards | `standards/` | Development classification, SDD, navigation, design, and documentation rules |
| Maintainer operations | `DEVELOPMENT.md`, `MAINTAINERS.md`, `TESTING.md`, `RELEASE_CHECKLIST.md` | Local development, validation, branch, release, and maintenance operations |
| Verification protocols | `TESTING.md`, Skill references, executable tests/fixtures | Repeatable inputs, commands, oracles, and evidence levels |
| Feature specs | `specs/<feature>/` | Feature requirements, accepted design, tasks, and verification |
| Lifecycle registry | `specs/registry.json` | Spec lifecycle, owner, and successor |
| Release history | `releases/`, `CHANGELOG.md` | Version-specific historical behavior |
| Evidence/archive | explicitly admitted records or archive paths | Independently useful audit evidence or historical explanation |

Public English docs remain flat to preserve established links. Directory shape
does not establish authority; the class and owner above do.

## Source-Of-Truth Order

```text
product outcome
  -> Capability Map
  -> Architecture / Active Contract
  -> Supporting Contract
  -> implementation and tests
  -> Verification Protocol / Evidence
```

- `CAPABILITY_MAP.md` owns capability ID, four-axis maturity, boundary, and one
  active owner.
- `ARCHITECTURE.md` owns layer taxonomy, dependency direction, and formal-host
  rules.
- `CONTRACTS.md` and its specialized contract documents own current authority,
  lifecycle, recovery, and publication boundaries.
- `harness/rules/semantic-hosts.json` is a machine projection of those
  contracts. It cannot introduce responsibility or override prose owners.
- `specs/registry.json` alone owns spec lifecycle.
- Harness/Git owns current development execution.

Indexes and projections link to truth; they do not copy completion matrices or
implementation narratives.

## Active And Supporting Contracts

An Active Contract declares its boundary, formal hosts, public/typed contract,
authority, state/lifecycle/recovery, verification, and open boundaries. A
semantic concern has only one Active Contract.

A Supporting Contract is admitted only when it has one stable delegated
responsibility, direct code/schema and verification anchors, and lowers
discovery cost. It points directly to its Active Parent. Supporting-to-
Supporting chains, second capability owners, and task-state copies are invalid.

## Content Excluded From Long-Term Contracts

- Initiative, stage, Gate, reviewer, or approval state;
- TaskPlan, RoleTask, progress log, or completed-controller narration;
- volatile test counts, durations, terminal output, temporary paths, or run IDs;
- migration chronology after the target contract is current;
- large copies of external articles, chats, repositories, or benchmark output;
- duplicated capability maturity;
- refactor plans justified only by file/helper/adapter size.

Open architecture boundaries are allowed when they name the missing owner,
behavior, or oracle rather than mutable task state.

## Lifecycle

| Action | Condition |
| --- | --- |
| Keep | Current unique owner with fresh, verifiable content |
| Update | Correct owner with stale boundary, anchor, or evidence |
| Merge | Content belongs to another owner or splitting increases discovery cost |
| Archive | No longer current but still has independent explanatory/audit value |
| Delete | Fully absorbed, duplicated, transient, or adequately retained by Git |

Before deletion, preserve stable contract in its target owner, migrate valid
code/test/verification anchors, update indexes and links, confirm no operation
exists only in the deleted file, and rely on Git for ordinary history.

## Change Process

Before adding a document, declare its class, unique owner or Active Parent,
audience, code/verification anchors, and deletion condition. If an existing
owner can carry it, update that owner.

For external references, the owning spec records `adopt`, `adapt`, `reject`, or
`defer`, with target owner, verification, and cleanup. The reference is evidence
and never a current-state documentation family.

At Direct SDD or Harness closure, promote only delivered deltas:

1. authority/host/state/recovery changes to the Active Contract;
2. stable delegated detail to an admitted Supporting Contract;
3. reusable acceptance to a Verification Protocol;
4. true maturity changes to the Capability Map;
5. mutable execution state stays in Harness/Git.

## Automated Governance

`scripts/check-doc-governance.py` validates registry integrity, required
standards, capability rows, semantic-host projections, Skill metadata, stale
Harness authorities, and forbidden current-document patterns.
`scripts/check-doc-links.py` validates repository Markdown links.

English is authoritative for current public and release documentation. Chinese
public guides and contracts remain paired when user-visible behavior changes.
Historical release notes remain historically accurate.
