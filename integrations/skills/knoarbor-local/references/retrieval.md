# KnoArbor Retrieval Guidance

Use query as candidate discovery, not as the final answer shape.

## Progressive Flow

1. Rewrite the user request into a short standalone search query.
2. Run `scripts/knoarbor.py query ...` with a compact standalone question.
3. Inspect `raw_evidence`, `context_pack`, `evidence_coverage`,
   `response_guidance`, `gap_suggestions`, and `gaps`.
4. Answer factual questions only from complete raw source units in
   `raw_evidence` or the raw-evidence section of `context_pack`.
5. Use `results` only to navigate to a maintained projection when the user asks
   to browse, inspect, or edit a page.
6. For broad summaries or comparisons, combine the selected raw units and mark
   cross-unit conclusions as inference.
7. If several candidates are plausible and the user's intent is ambiguous, list
   2-5 candidates with title, path, and reason, then ask the user to choose.
8. If matches are weak, try a shorter or alternate query once. If still weak,
   say the local wiki does not contain enough evidence and ask a clarifying
   question or use another source.

Compact context is the default evidence layer for the host AI to judge
relevance. Do not present it as a user-facing answer by itself.

## Query Versus Chat

`query` is the default retrieval operation for this skill. It is model-free,
fast, and returns optional projection locators, claim-backed raw evidence,
coverage signals, and a context pack for the host AI to evaluate.

KnoArbor also exposes `/chat` for the local web console. That endpoint runs a
bounded Wiki Chat Agent and synthesizes an answer itself. Host AI skills should
not use `/chat` for ordinary answers because the host AI is already responsible
for synthesis. Prefer `/chat` only when a user explicitly asks to use the
KnoArbor console chat behavior.

## When To Read Full Pages

Use `page read` when:

- the user gives a page path or selects a previous result;
- the user asks for a full page, original text, detailed page analysis, or
  section-by-section review;
- the user wants to inspect a projection associated with a query locator;
- the task needs page structure, exact wording, frontmatter, tables, or long
  lists.

Do not automatically read many pages in full. When more than 2-3 pages may be
needed, list candidates first and let the user pick a scope.

When a query result includes `vault_id`, pass that same vault ID to `page read`
or `page relations`:

```bash
python3 scripts/knoarbor.py --vault-id <result.vault_id> page read <result.path>
python3 scripts/knoarbor.py --vault-id <result.vault_id> page relations <result.path>
```

This keeps follow-up reads in the same knowledge base as the selected result.

## Query Fields

- `results[].path`: optional projection path for navigation or `page read`.
- `results[].vault_id`, `vault_name`, `vault_path`: selected result provenance
  for multi-vault follow-up reads.
- `results[].reason` and `atom_traces`: non-factual retrieval explanation.
- `raw_evidence`: complete active source units and stable evidence identities.
- `context_pack`: raw-evidence bundle plus non-factual locator trace.
- `gaps` and `gap_suggestions`: weak or missing local context signals.

## Multi-Vault Follow-Up

For multi-vault query results, preserve the selected result's vault context.
The result path is only unique inside its own knowledge base.

Recommended sequence:

1. Query with `--all-vaults` or repeated `--query-vault-id`.
2. Present candidate titles with `vault_name` and `path`.
3. When the user selects a candidate, call `page read` or `page relations` with the
   selected result's `vault_id`.

Example:

```bash
python3 scripts/knoarbor.py query "iOS 音频检测" --all-vaults
python3 scripts/knoarbor.py --vault-id work page read iOS-Audio-Detection.md
```

## Evidence Synthesis

- Cite stable evidence identities or source paths near important claims; use
  projection page paths only for navigation.
- Treat KnoArbor as local memory. For unstable current facts, newer external
  sources can override older wiki pages.
- If wiki evidence conflicts with current sources or with another wiki page,
  state the conflict instead of silently merging both.
- Use source digest pages as provenance. Maintained wiki knowledge lives in
  `wiki/pages`, while source audit material lives in `wiki/sources`.
