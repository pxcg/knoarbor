# 1.5 Knowledge Governance Verification

## Required Automated Checks

```bash
.venv/bin/python -m unittest \
  tests.test_lint_pipeline \
  tests.test_lint_api \
  tests.test_lint_semantic_workflow \
  tests.test_knowledge_atom_lint
./scripts/dev-check.sh
```

## Required Behavioral Proof

- deterministic lint detects structural and atom-index defects;
- semantic models produce findings and repair plans rather than replacement content;
- lint automatically executes approved repairs through owner workflows;
- repeated findings for one canonical source trigger one reingest;
- reingest reads the exact immutable input generation owned by the active
  revision;
- projection and index findings share one materialization pass;
- a deterministic rescan records post-repair integrity;
- projection edits publish a new canonical revision rather than writing the
  generated Markdown file directly;
- raw evidence and identity edits are rejected before publication;
- edited fields survive later raw ingest through the active revision metadata;
- semantic lint does not compile or write page drafts;
- provenance findings do not create source pages;
- generated projection content is unchanged by semantic lint;
- report and ledger artifacts contain the normalized request type, evidence,
  target, and reason;
- no model call is introduced for deterministic integrity decisions.

## Manual Temporary-Vault Smoke

1. Create a vault with one valid ingest publication.
2. Record hashes for raw, facts, atom index, and generated pages.
3. Introduce one derived projection or index defect.
4. Run lint.
5. Confirm the finding maps to a rebuild request.
6. Confirm raw and canonical fact hashes are unchanged.

## 2026-07-12 Evidence

- All nine local development gates passed, including 561 Python tests,
  renderer build, Playwright smoke, documentation governance, and package build.
- Focused lint tests pass against the automatic owner-routed repair contract.
- A real active ingest vault scanned 1 source record, 10 source units, 10 raw
  evidence records, 46 atoms, and 1 projection with 0 integrity issues.
- Full semantic page content is supplied when semantic diagnosis is requested;
  no fixed character or candidate-count truncation is active by default.
- Public Python, CLI, UI, and skill contracts expose no page-patch or optional
  auto-apply switch; automatic owner-routed repair is the single behavior.
- A transactional integration test commits canonical facts, corrupts the
  generated projection, runs deterministic lint, and proves materialization
  restores the projection with zero post-repair issues.
- The production tree contains no lint draft-compile contract, provenance
  refresh executor, or active semantic page-write route.
- Full local gates passed: renderer build, dependency audit, Playwright smoke,
  Ruff, documentation links/governance, 560 Python tests, CLI diagnostics, and
  Python package build.
