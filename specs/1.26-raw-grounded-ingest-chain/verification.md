# 1.26 Raw-Grounded Ingest Chain Verification

## Ownership Matrix Tests

- Model schema contains only semantic strings, verbatim claim evidence quotes,
  and request-local positions.
- Relation candidates contain endpoints, predicate, and supporting claims, with
  no relation evidence positions.
- Code validates every claim quote and creates every stable ID, persisted
  evidence excerpt, source location, path, hash, attachment technical field,
  and thumbnail reference.
- Synthesis is named and described only as retrieval-locator metadata.
- Bilingual source material emits a `mixed` document hint plus language-local
  unit hints, and prompt policy forbids output-wide language homogenization.
- Deterministic compilation contains no language classifier or
  language-mismatch issue type; a grounded fake extraction is not rejected
  solely because its metadata language differs from the source hint.
- Deterministic compilation contains no open-predicate conflict heuristic,
  unused-entity issue, or missing-synthesis warning. Grounded standalone
  entities and empty synthesis remain valid.

## Compiler Tests

Cover empty extraction, malformed strict positions, unsupported aliases,
unknown references, pronoun-linked claims, relations with zero/one/multiple
supporting claims, overlapping evidence, repeated segments, delayed segment
completion, directionally distinct relations, paraphrased claims with exact
source quotes, missing quotes, repeated quotes, and Chinese/English units
inside one bilingual source.

Assert:

- no model position survives compilation;
- each claim evidence range equals its validated source quote and never widens
  to the full source unit after a failed match;
- CJK layout wraps map to the exact enclosing Raw slice while blank lines,
  punctuation changes, horizontal-whitespace changes, and OCR substitutions
  are rejected;
- one invalid claim quote rejects only that claim and its unsupported
  relations; accepted claims retain their original candidate identities;
- persisted evidence with an invalid unit range fails hydration instead of
  returning the complete unit;
- repeated and overlapping quotes compile successfully, with repeated text
  mapped to the first source occurrence;
- relation evidence exactly equals the ordered deduplicated evidence union of
  accepted supporting claims;
- segment order or concurrency does not change IDs or output;
- rejected candidates never become facts through a fallback path;
- synthesis composition preserves unique batch locator text in source order.

## Artifact Tree Tests

For one committed source, assert the exact active tree:

```text
.knoarbor/facts/<source-key>/<revision-key>/
  source.json
  knowledge.json
  diagnostics.json
  manifest.json
```

Validate every schema, manifest file list, hash, relative path, and source-head
reference. Assert that no model output controls a path or filename.

## Projection Golden Tests

Golden cases cover:

- a short source with one claim and evidence;
- a long segmented source with stable human Cn/Rn labels;
- entities with and without aliases;
- a relation supported by multiple claims;
- no entities or relations;
- image attachment with topic, description, and thumbnail;
- attachment with missing optional labels;
- attachment path or thumbnail that fails local validation.

Assert that projection body contains only approved fields, contains no internal
IDs or diagnostics, creates no broken unconditional entity link, and remains
byte-identical across two rebuilds.

## Migration And Recovery Tests

- Migrate legacy active fact generations without a semantic call.
- Restart after every file-copy, rename, manifest, and SQLite-head boundary.
- Preserve source identity, units, aliases, synthesis, claims, relations,
  evidence, attachments, and diagnostics.
- Reject corrupted legacy or target payloads rather than selecting a fallback.
- Remove the legacy tree after successful migration and prove current readers
  do not access it.
- Delete projection and machine index trees, rebuild, and require zero model
  calls.

## Fake End-To-End Test

Run the real input resolver, semantic boundary, compiler, linker, publisher,
materializer, raw API, page API, and retrieval stack in a temporary vault.
Inspect model payload, fact files, extraction projection, raw default view, and
machine index. Repeat unchanged input and require zero semantic calls.

For local Markdown attachments, cover both standard image links and Obsidian
image embeds. Verify unique source-root resolution, rejection of missing and
ambiguous filename-only embeds, content-addressed copy into
`raw/derived/assets`, removal of external paths from the immutable input
document, rendering after the original source tree is removed, preservation of
ordinary Wiki links, and literal display of unresolved image embeds.

## Real-Model Audit

Before live-model coverage, apply privacy redaction to an attachment whose
SHA-256 and retained filename contain a phone-shaped digit run. Require
byte-identical machine identity, redacted descriptive phone text, and a
resolvable retained asset.

Use fixed short and long local documents. For every accepted entity, alias,
claim, relation, synthesis, and ambiguity, verify source support. Verify each
claim evidence excerpt and each relation evidence derivation. Inspect attachment
metadata separately from model output. Remove temporary source copies, fact
trees, projections, reports, and indexes after the audit; leave original files
unchanged.

## Performance And Storage

For representative personal-knowledge sources, record raw bytes, fact bytes,
projection bytes, index bytes, elapsed deterministic time, semantic time, and
peak memory. Require linear deterministic work in source units plus accepted
elements and prohibit embedded duplicate attachment binaries in fact JSON.

## Required Commands

```bash
uv run python -m unittest \
  tests.test_semantic_contracts \
  tests.test_ingest_profiles \
  tests.test_entity_registry \
  tests.test_source_revisions \
  tests.test_wiki_pages
uv run python -m unittest \
  tests.test_markdown_connector \
  tests.test_ingest_inputs \
  tests.test_wiki_pages
uv run python -m unittest discover -s tests
uv run --extra dev ruff check src tests scripts
uv run python scripts/check-doc-governance.py
uv run python scripts/check-doc-links.py
git diff --check
```

## Compiler Validation Clean-Path Verification

- Entity primary-name occurrence is candidate-local and exact against cited
  evidence.
- Compiler postcondition corruption produces a typed internal source failure.
- Dry-run and write agree on `processed` versus all-claims-rejected `partial`.
- Runtime schemas, reports, diagnostics, and tests contain no quality gate,
  approved-segment list, aggregate rejected-annotation warning, or `rejected`
  source/segment state.
