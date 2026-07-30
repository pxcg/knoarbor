# 1.10 Wiki Chat Verification

## Focused Backend

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_chat_agent \
  tests.test_chat_sessions \
  tests.test_chat_tool_flows \
  tests.test_chat_execution_safety \
  tests.test_chat_stream \
  tests.test_chat_memory \
  tests.test_chat_support_spans
```

Required assertions:

- ordinary candidates use one Retrieval Planner, one Query batch, one Answer
  Decision, and one Response Composer call;
- trustworthy combined no-match never triggers a second planner or batch;
- the planner resolves follow-up references and cross-language expressions
  while code retains the literal question in the same region group;
- adding or reordering selected regions cannot duplicate one active Raw
  identity in the answer evidence;
- a region executes the ordinary Query pipeline, filters only that
  expression's candidates to the selected source units, and cannot admit a Raw
  unit solely because it belongs to the selected region;
- planner output contains only exact visible region IDs plus one regional query
  and cannot name a coverage mode, retrieval channel, or graph algorithm;
- the planner receives locator-only active catalog metadata and language hints without Raw content,
  claim prose, entities, aliases, relation predicates, attachment names,
  internal revision IDs, or evidence IDs;
- an invented region ID enters configured retry, and planner failure still
  executes one unscoped unchanged expression;
- a clearly Chinese expression for an English region, or vice versa, enters
  configured retry instead of silently defeating lexical recall;
- candidate/gap/no-match/failure provenance stays typed; candidates and
  no-match invoke the same fixed decision/composer sequence without another
  Query;
- Query diagnostics record BM25/RRF window membership and exact structural
  evidence reasons without a Chat-owned score, threshold, winner, or
  source-membership admission rule;
- normalized expressions without searchable terms return `invalid_query`;
  ordinary domain nouns and technical-identifier clauses remain Query-owned
  BM25 inputs rather than a second eligibility gate;
- Query owner tests assert direct relevance, region source-unit restriction,
  active Raw deduplication, and unrelated-query no-match;
- Answer Decision accepts only the five-field schema and valid raw/general/gap
  combinations; Response Composer cannot change that authority;
- structural checks prove no candidate-level model judge remains;
- unknown, duplicate, stale, or unauthorized support spans are rejected;
- code injects one adjacent marker per selected Raw unit, collapses overlapping
  or touching ranges, preserves disjoint ranges inside that citation, and
  preserves Raw identity;
- complete substantive dialogue history includes only user questions and final
  assistant answers after code-rendered citation markers, source/generated
  image Markdown, and generated-image labels are removed;
- retry reruns the full turn and atomically replaces it;
- v3 sessions migrate to v4 without losing dialogue, provenance, citations,
  images, lifecycle, or ingest metadata;
- migrated v3 sessions with turn-local traces retain those traces and clear the
  duplicated session-level trace;
- session listing obtains canonical v3/v4 summaries without invoking the full
  record reader, paginates through older summaries without omission, and a full
  legacy read removes duplicated Raw trace content;
- switching session or vault closes the previous citation preview and
  invalidates late preview responses;
- dynamic image capability remains conditional and image failure does not erase
  a valid text answer.
- image requests pass through Query and Answer Decision; generation requires a
  validated decision plus one composer-authored prompt.
- Answer Decision prompts expose call-local visual references, source-authored
  captions and processor-extracted visual content but no durable attachment ID,
  filename, MIME type, hash, or render path;
- caption-only and extracted-content-only images remain eligible, while images
  with neither remain stored but receive no visual reference and do not render;
- Raw-linked images selected with same-Raw support become mandatory composer
  inputs; every selected visual renders exactly once after preceding text uses
  its owning material, while omitted, unknown, repeated, before-owner, and
  cross-Raw references fail validation;
- optional generated images render with a code-owned visible label stating
  that they are not knowledge-base evidence.
- structural searches find no live unified Final Answer prompt/schema,
  no-match gate, local-evidence regex, separate general prompt, or
  grounded/general answer synthesizer.

## Renderer

```bash
cd renderer
npm run build
```

The renderer must emit v4 requests, parse v4 responses/sessions, preserve
stream completion, and send no `max_turns`. Citation sources must be grouped by
document, report document/excerpt counts, keep disjoint excerpts independently
selectable, and highlight all answer-selected spans in the selected document.
Reloaded locator-only citations must resolve temporary highlight text from the
identified source unit without adding excerpts to session JSON. Invalid or
missing locators must leave Raw unhighlighted and must never slice full Raw with
source-unit-local offsets.

## Structural Residual Check

Live source and renderer code must contain no implementation reference to:

```text
ChatTopicAnchor
chat_topic_anchor
chat_turn_intent
question_dimensions
dimension_coverage
retrieval_continuation
max_turns
chat_request.v3
chat_response.v3
chat_session_retry_request.v3
```

The only permitted `chat_session.v3` reference is the explicit v3-to-v4
migration and its fixture.

## Governance

Run the affected-validation planner, documentation governance checks, link
checks, and the tests selected for the changed dependency closure. Desktop
packaging and real-provider acceptance are separate user-requested release
checkpoints.

## Comprehensive Acceptance v2

```bash
uv run python scripts/comprehensive-chat-eval.py validate-definition
uv run python -m unittest \
  tests.test_comprehensive_chat_gold \
  tests.test_comprehensive_chat_eval
```

Required assertions:

- the v2 corpus contains 17 retained document identities and the v2 Gold
  contains 76 unique cases;
- every case has one uniform schema, one primary scenario, independent
  dimensions, explicit latest-message response language, history/runtime
  objects, and terminal/decision/composer expectations;
- decision expectations use only `raw`, `general`, or `gap`, except typed
  terminal failures that bypass semantic decision;
- stable Raw and source-visual caption anchors belong to expected documents;
  request-local span, visual, material, evidence, and attachment IDs are absent;
- generated-image intent is true only for the explicit case set, and generation
  without explicit latest-message intent is a hard failure;
- parent chains are present, acyclic, and ordered before their dependents;
- the same-title version pair covers explicit latest-version selection,
  attributed comparison, and an unqualified conflict response;
- reviewed live results report retrieval, Answer Decision, Response Composer,
  evidence precision, visual provenance, answer usability, and hard failures
  separately for every case;
- definition validation and unit tests require no live provider, private source
  root, or user vault.
