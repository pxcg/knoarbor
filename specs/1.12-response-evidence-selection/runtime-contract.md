# Runtime Contract

This spec freezes the runtime boundary between query retrieval, chat evidence
planning, and public citation presentation.

## Query Response

`WikiSearchResponse` uses `schema_version = wiki_query.v1`.

Stable answer-bearing fields:

- `results`: ranked candidates returned by retrieval.
- `primary_pages`: maintained pages that directly carry the answer.
- `supporting_pages`: maintained pages that add complementary evidence.
- `source_pages`: source digest pages for provenance.
- `answer_scope`: deterministic query breadth and vault scope.
- `answer_set`: selected page-role plan.
- `evidence_coverage`: deterministic coverage and gap signal.
- `context_pack`: prompt-ready evidence text for host callers.

`results` remains a candidate surface. `answer_set` remains the answer-planning
surface. `context_pack` is a transport projection of the selected evidence.

## Chat Evidence Pack

`ChatEvidencePlanner` emits `schema_version = chat_evidence_pack.v1`.

Stable model-facing fields:

- `primary_pages`
- `supporting_pages`
- `source_pages`
- `citation_pages`
- `further_results`
- `answer_scope`
- `answer_set`
- `evidence_coverage`

`citation_pages` defines the reference order visible to the answer model.
`further_results` carries navigation material and follow-up options.

## Public Citations

`ChatReferenceResolver` owns answer-visible citation presentation.

Resolution rules:

- Inline references such as `[1]` are resolved against `citation_pages`.
- Sparse references are normalized to consecutive public numbers.
- Model-selected citations are validated against observed tool evidence.
- `list_wiki_pages` observations are navigation evidence; they become public
  citations only when the answer explicitly references them.
- `hidden_evidence_count` records observed evidence outside the public citation
  list.

## Verification

`tests/test_runtime_contracts.py` checks:

- stable ingest observation step names;
- stable query response contract constants;
- stable chat evidence pack keys;
- citation resolver behavior for hidden evidence and renumbering.
