# 1.5 Knowledge Governance Verification

## Automated Checks

Required when lint governance changes:

```bash
uv run python -m unittest tests.test_lint_pipeline tests.test_lint_api tests.test_operation_pipeline tests.test_operation_verification tests.test_lint_semantic_workflow
uv run python scripts/check-doc-links.py
```

Add or keep golden tests for:

- deterministic issues;
- reviewed semantic operations;
- rejected/deferred candidates;
- diff reporting;
- post-write verification;
- repeated issue history once implemented.

## Manual Smoke

Use a temporary vault with known structural and provenance issues:

1. Run deterministic lint.
2. Run full lint with model access.
3. Confirm safe fixes apply automatically.
4. Confirm complex changes show review decisions.
5. Confirm report lists changed pages and before/after diffs.

## Regression Risks

- Automatically applying unsupported operations.
- Hiding rejected operations without clear follow-up state.
- Producing UI-only evidence that CLI/API users cannot access.
- Retrying deterministic policy failures as if they were transient model errors.

## Release Evidence

For a 1.5 release note, mention:

- governance operation taxonomy changes;
- automatic repair behavior;
- diff/report improvements;
- quality and repeated-issue tracking.
