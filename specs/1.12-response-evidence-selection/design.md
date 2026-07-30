# 1.12 Response Evidence Selection Design

## Lifecycle

Superseded by `1.38-semantic-indexed-raw-query`. The `AnswerSetSelector`
described below has been removed from default query.

## Layer Position

```text
MachineIndexProvider
  -> QueryPipeline candidate retrieval
  -> page-level structural scoring
  -> AnswerSetSelector
  -> evidence coverage
  -> context pack / chat evidence pack
```

The selector receives already-ranked `WikiSearchResult` candidates. It does not
read files, call models, or run additional retrieval. It produces a selection
plan that assigns candidate pages to answer roles.

## Selection Contract

The selector returns:

- `primary_paths`: pages that can directly answer the current question.
- `supporting_paths`: pages that add necessary mechanisms, implementation
  details, comparisons, caveats, or adjacent context.
- `source_paths`: source record pages used for provenance.
- `further_reading_paths`: relevant pages that are useful follow-up material
  but should not shape the answer.
- `rejected_candidates`: pages considered but excluded from the answer set,
  with a reason.

## Deterministic Signals

The first implementation uses structural signals:

- query scope: narrow, broad, exploratory;
- page role and directory;
- source query intent;
- score distance from the strongest answer page;
- direct match versus graph expansion;
- matched fields such as title, summary, claims, relations, entities, and body;
- evidence diversity from page role, directory, entities, headings, and graph reasons;
- source record role.

## Primary Selection

Rules:

- Source pages are primary only when source/provenance intent is detected or no
  maintained knowledge page matched.
- Narrow questions select one primary page by default.
- Broad and exploratory questions may select multiple primary pages only when
  they are strong, direct, and evidence-dimension-distinct.
- A high-scoring page that is mostly redundant becomes supporting or further
  reading rather than another primary page.

## Supporting Selection

Supporting pages are selected when they add complementary evidence dimensions. The selector
prefers direct matches, graph-linked pages, pages with shared source, and pages
with non-overlapping entities, headings, and relations. Redundant pages are rejected or moved
to further reading.

## Rejection Reasons

Common reasons:

- `source_not_requested`
- `redundant_dimension`
- `weak_score`
- `not_answer_bearing`
- `outside_answer_budget`

Rejected candidates are part of trace metadata. They are not sent to the model
as default answer evidence.

## Why Not LLM Rerank

LLM rerank can be added later for low-confidence or high-value flows, but the
default selector should be deterministic. This keeps query latency low, makes
skill calls model-free, and keeps the page selection explainable.
