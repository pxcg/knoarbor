# Public Product Line Convergence Verification

Status: Accepted

## Baseline And Ancestry

```bash
git merge-base --is-ancestor company-project/SieArbor HEAD
test "$?" -eq 1
git merge-base --is-ancestor origin/main HEAD
git rev-list --objects origin/main..HEAD
```

Review every candidate commit and reachable added object. The private branch
head must not be an ancestor.

## Governance

```bash
python3 scripts/check-doc-governance.py
python3 scripts/check-doc-links.py
git diff --check
```

The registry, requirements, design, tasks, verification, ADR index, and stable
owner links must agree.

## Product Identity

Required automated evidence:

- manifest schema rejects missing, unknown, and ill-typed fields;
- generation is deterministic and `--check` detects drift;
- Python, Renderer, Electron, and packaging values match the manifest;
- environment overrides are restricted to documented fields and one prefix;
- public tree and generated artifacts contain no private product markers.

Focused commands:

```bash
python3 scripts/generate-product-identity.py --check
python3 scripts/check-public-product-boundary.py
uv run --extra dev python -m unittest -q \
  tests.test_product_identity tests.test_core_config tests.test_ui_api
npm --prefix renderer run build
npm --prefix desktop run typecheck
npm --prefix desktop test
```

## Persisted Migration

Historical fixtures must cover:

- KnoArbor 2.3.1 config and desktop data root;
- vault layout and source records;
- completed, failed, and interrupted ingest state;
- indexes and projections that require deterministic rebuild;
- chat sessions and citation records.

Each fixture verifies compatibility, idempotent migration, explicit rejection,
or a declared breaking outcome. Original fixture state must remain recoverable
after an injected migration failure.

## Domain Closure

Each transfer slice runs its owner tests and direct consumers. The final
candidate additionally verifies:

- ingest, deletion, reingest, recovery, and deterministic materialization;
- active-Raw query, graph closure, evidence reads, and exact support spans;
- Chat retrieval, citations, source/generated images, editing, and persistence;
- renderer vault switching, Markdown preview, highlights, and user-facing
  errors;
- desktop startup, shutdown, upgrade, backup, packaging, and data preservation;
- API, CLI, config, report, and skill parity.

## Security And Public Leakage

Scan the public tree, candidate history, source archives, renderer output, and
desktop packages for:

- `SieArbor`, Siemens identifiers, and private product assets;
- intranet hosts, private update metadata, and private provider defaults;
- credentials, tokens, local runtime data, and internal-only documentation.

Any intentional historical comparison must be confined to this specification
or ADR and reviewed before release documentation is generated.

## Release Acceptance

Run the repository's affected planner after it is ported, then execute the
actual R3 dependency closure. Before release, run clean-clone and source-package
checks, public macOS/Windows packaging, migration acceptance, and the KnoArbor
full-chain acceptance workflow.

Record exact commands, commit OID, platform, result, and unresolved residual
risk before marking the specification Implemented.

## Compatibility And Release Decision

| Contract | Decision | Evidence |
| --- | --- | --- |
| KnoArbor 2.3.1 config and vaults | Automatically migrated | Historical config, vault, ingest-state, and revision-integrity fixtures |
| Public Python package, CLI, and HTTP API | Compatible additions with typed outcomes | Python owner and API-surface tests |
| Renderer and desktop IPC | Coordinated 2.5.3 contract update | Renderer E2E and desktop contract tests |
| Desktop application data | Preserved; uninstall never deletes external vaults | Desktop lifecycle and installer tests |
| Private updater and provider defaults | Explicitly rejected | Public-boundary scan and updater-free package graph |

The public release is `2.5.3`: a public minor-line convergence from 2.3.1 with
automatic persisted migration. The number describes the KnoArbor contract and
does not import private release ancestry.

## Delivery Record

The implementation was validated on macOS arm64 from public baseline
`18fde631`. Ordinary Git/SDD delivery was used; the optional Initiative Harness
was not invoked.

Required closure commands:

```bash
./scripts/dev-check.sh
./scripts/clean-clone-smoke.sh
npm --prefix desktop run pack:mac
npm --prefix desktop run pack:win
python3 scripts/check-public-product-boundary.py
git diff --check
git merge-base --is-ancestor 18fde631 HEAD
git merge-base --is-ancestor 53da106c HEAD  # expected non-zero
```

The macOS package must report `ai.knoarbor.desktop`, version `2.5.3`, pass
strict code-signature structure verification, launch its bundled service
binary, and contain no private marker in authored resources. Windows packaging
must run on a native Windows host: the command now fails before preparation on
macOS or Linux so a Mach-O/ELF service cannot be silently embedded in a Windows
shell. Windows icon, application identity, installer, lifecycle, and
fail-closed host contracts are covered by the desktop automated suite; a
native Windows release runner remains required for a distributable `.exe`.
