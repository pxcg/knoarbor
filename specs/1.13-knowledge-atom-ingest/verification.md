# 1.13 Knowledge Atom Ingest Verification

## Automated

- `KnowledgeAtomBatch` accepts facts with evidence.
- Facts without evidence fail validation.
- Claims without evidence and supporting facts fail validation.
- Relations without evidence, supporting facts, or supporting claims fail
  validation.
- Atom batch summaries report fact, claim, relation, and evidence counts.
- Existing ingest tests pass while the atom layer is introduced.

Current verification commands:

```bash
uv run python -m unittest \
  tests.test_ingest_context \
  tests.test_ingest_compile_context \
  tests.test_semantic_contracts \
  tests.test_ingest_semantic_workflow \
  tests.test_ingest_pipeline \
  tests.test_semantic_golden \
  tests.test_source_digest \
  tests.test_knowledge_atoms \
  tests.test_knowledge_atom_quality

uv run ruff check \
  src/knoarbor/core/schemas/knowledge_atoms.py \
  src/knoarbor/core/schemas/source_digest.py \
  src/knoarbor/semantic/source_digest.py \
  src/knoarbor/semantic/contracts.py \
  src/knoarbor/semantic/ingest_workflow.py \
  src/knoarbor/pipelines/ingest.py \
  src/knoarbor/audit/ingest_report.py \
  tests/harness/semantic_cases.py \
  tests/test_semantic_contracts.py \
  tests/test_ingest_semantic_workflow.py \
  tests/test_semantic_golden.py \
  tests/test_knowledge_atoms.py \
  tests/test_knowledge_atom_quality.py \
  tests/test_source_digest.py \
  tests/test_ingest_pipeline.py
```

## Manual

- Ingest a small Markdown source and inspect the report for atom extraction
  counts once P2 lands.
- Verify source digest pages remain readable.
- Verify generated wiki pages remain readable and do not expose raw atom ids in
  the default view.
- Verify page claims can be traced to source digest or source evidence in debug
  surfaces.

## Release Gates

- The atom layer must not change public API response shapes until the API spec
  is explicitly updated.
- Existing vault Markdown pages must continue to render in the frontend.
- Existing query/chat flows must continue to answer from pages when atom index
  files are missing.
- Migration must be additive until reports show atom quality is stable.

## Known Risks

- Over-extraction can create noisy facts and claims. Mitigation: extract only
  durable, reusable atoms and reject unsupported atoms.
- Atom ids can become unstable if derived from model wording. Mitigation:
  derive ids from normalized statement plus evidence hash where possible.
- Page prose can drift away from atom evidence. Mitigation: lint page claims
  against source digest ids and atom ids after P4.
- Report complexity can overwhelm users. Mitigation: keep atom details in
  technical sections and show summary counts by default.
