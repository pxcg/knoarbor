# 1.10 Wiki Chat Design

## Runtime Flow

```text
ChatRequest v4
  -> validate scope and session revision
  -> direct product capability, when explicitly applicable
  -> Query-derived document/chapter outline from active source records
  -> Retrieval Planner(dialogue, latest question, outline with language hints)
  -> retrieve_knowledge_batch(
       [literal + regional expression grouped inside each selected region]
     )
       -> candidates or trustworthy no_match:
          -> Answer Decision(mode + selected support/visuals + gap + image intent)
          -> validated selected-material projection
          -> Response Composer(ordered text/source-visual items)
       -> typed failure/gap: non-general terminal route
  -> support-span and citation validation
  -> optional source/generated image projection
  -> atomic ChatSession v4 persistence
  -> ChatResponse v4
```

The optional Retrieval Planner reads only the dialogue projection and locator
outline, then returns exact visible document or chapter `region_id` values plus
one standalone expression for each region. Code validates those IDs and sends
both the unchanged latest question and the regional expression inside one
shared region group. Query evaluates Raw lexical, atom/claim, entity, and applicable
relation locators within each region and fuses the results. Region membership
cannot authorize or force-admit Raw. Empty or unavailable planning degrades
to one unscoped unchanged question. The model may resolve dialogue references
and translate for the selected region, but it never sees or judges candidates.

## Ownership

| Owner | Responsibility |
| --- | --- |
| Chat | dialogue, orchestration, answer invocation, support/provenance validation, citation rendering, persistence |
| Query 1.38 | active document/chapter outline, region filtering, recall, ranking, fusion, structural evidence selection, active resolution, typed outcomes, exact Raw segments returned to Chat |
| Prompt 1.18 | dialogue-aware Retrieval Planner, minimal Answer Decision, and Response Composer structured outputs |
| Model gateway | provider adaptation, retry, streaming, token metrics |
| Renderer | progress, answer, source labels, citations, session lifecycle |

Chat does not rerank Query evidence or choose a best-k. Query owns recall,
fusion, structural selection, Raw resolution, and evidence volume. Chat passes
the Query-authorized Raw bundle, typed retrieval outcome, original question,
and dialogue-only history to Answer Decision. That stage chooses Raw-grounded,
general, or gap authority and complete non-redundant support/visual material. Code
validates and projects only selected exact Raw in source order, one code-owned
reader-facing source label, and selected visual semantics into call-local
material IDs for Response Composer. The composer writes the answer without re-deciding
relevance, evidence, or authority.

## Answer Contract

Answer Decision:

```json
{
  "mode": "raw",
  "spans": ["sp_1_1"],
  "visuals": ["visual_1_1"],
  "gap": null,
  "generated_image_prompt": null
}
```

Code validates any generated-image prompt and invokes the provider before
Response Composer.

Response Composer:

```json
{
  "items": [
    {
      "type": "text",
      "markdown": "Supported answer text.",
      "materials": ["material_1"]
    },
    {
      "type": "source_visual",
      "visual": "visual_1_1"
    },
    {
      "type": "generated_visual",
      "visual": "generated_visual_1"
    }
  ],
  "gap_markdown": null
}
```

Each decision span must be known and authorized; every decision visual must
belong to a Raw source with selected support. Code groups the flat selection by
authoritative Raw ownership and gives the composer only selected Raw text,
code-owned source labels, and selected visual semantics under temporary
material IDs. Successful generated images are projected separately as
request-local visual references with semantic descriptions and generation
status; paths and Markdown remain code-owned. The composer must use every
selected material and every supplied visual exactly once. Each source visual
appears only after preceding text establishes its owning material; generated
visuals may appear wherever they naturally support the response. The composer
otherwise controls reading order and final expression.

Code determines public citation numbering and placement. One marker represents
one active Raw source unit. Its locator retains all exact selected ranges:
overlapping or touching ranges may collapse, while disjoint ranges remain
separate. General mode carries no materials or source visuals. Gap mode carries
no factual text or source visuals, but may carry a successfully generated visual.
Raw mode may carry a partial gap. Optional generated assets require a
decision-authored prompt and receive a code-owned non-evidence label.

## Dialogue

Retrieval Planner, Answer Decision, and Response Composer receive the complete
substantive persisted dialogue projection:

```json
[
  {"user": "question", "assistant": "final answer"}
]
```

Code-rendered citation markers, source/generated image Markdown, generated
image labels, prior citation objects, evidence, tool traces, retrieval state,
and attachments are not included. History supports reference resolution and
conversational continuity but never becomes factual authority. Only Answer Decision receives
the complete current Query evidence projection. Response Composer receives the
selected exact Raw subset and selected source visuals, never the rejected
candidates or Query diagnostics.

The Retrieval Planner additionally receives the current locator-only document/chapter
outline. It contains deterministic region IDs, document display names,
the complete document-level synthesis, top-level chapter titles, and derived
dominant-language hints from active source processing and atom records. The
synthesis helps locate a document whose headings do not match the user's
wording; it is never factual answer material. The outline contains no Raw
content, claim/entity/relation rows, attachment names, internal
revision/evidence identities, or other projection prose.

## Persistence

`chat_session.v4` stores final product state, not orchestration state. It keeps
messages, turns, provenance, citations, artifact references, compact trace,
usage, lifecycle, and ingest metadata. It has no topic anchor, dimensions,
coverage, frontier, cursor, or continuation.

The v3 reader performs one in-memory migration before v4 validation. The v4
writer never emits v3 fields. Retry starts a fresh run and replaces the target
turn only after success.

Session listing reads the canonical top-level summary prefix that precedes
`turns`; it does not parse turn transcripts or traces before applying the list
page. The ordered summary collection exposes `offset`, bounded `limit`,
`total_count`, and `has_more`; the renderer follows continuation until every
sidebar summary is reachable. Noncanonical or malformed records use the
ordinary validated reader as a compatibility fallback. A full v3 read compacts
duplicated Raw content from legacy tool traces in the in-memory v4 record, and
the next write persists only the compact trace. When validated turn-local
traces exist, the duplicated legacy session-level trace is discarded entirely;
turn-local trace remains the sole trace authority.

Citation preview is session-local renderer state. The session lifecycle clears
and invalidates it before reading another session or starting another scoped
conversation. Preview reads carry an owner generation; completion is ignored
after another citation or session transition claims that owner.

The renderer presents one source collection grouped by physical source
document. A document row reports its number of answer-selected excerpts; each
excerpt remains independently selectable. Opening a document highlights all
of its selected spans in frozen Raw, while opening an excerpt additionally
scrolls that excerpt into focus. Retrieval candidates that were not selected
by the grounded answer never enter this collection.

Persisted citations contain only immutable Raw/source-unit identities and
answer-selected ranges. On preview, the Chat citation resolver loads the
identified source unit, interprets the range in that unit's coordinate space,
and returns temporary support text for renderer highlighting. The renderer does
not persist that text and never slices complete Raw with a source-unit-local
range. Missing or retired source material therefore produces an unhighlighted
preview instead of a false highlight.

## Failure And Finalization

- greetings, help, and vault listing may use direct product capabilities;
- image creation stays on the normal mainline; only validated Answer Decision
  intent can authorize the provider and only Response Composer can write the
  prompt;
- `candidates` and trustworthy `no_match` enter the same Answer Decision and
  Response Composer sequence;
- Raw mode may contain selected spans, selected visuals, and an explicit
  partial gap;
- general mode contains no Raw references; gap mode contains no response items;
  mixed authority is rejected;
- index, integrity, timeout, cancellation, resource, or unusable-evidence
  failures never masquerade as no-match.
- optional image failure preserves a validated text answer with a warning.
- either answer-stage failure persists no completed replacement turn.

## Public Surface

`POST /chat` and `POST /chat/stream` accept `chat_request.v4`; the stream final
event contains `chat_response.v4`. Session retry accepts
`chat_session_retry_request.v4`; persisted sessions use `chat_session.v4`.
There is no `max_turns` request field.

## Comprehensive Acceptance Design

The comprehensive Chat baseline is a maintainer-owned projection of this
runtime contract, not another answer authority. Version 1 remains frozen as
historical evidence. Version 2 consists of:

```text
comprehensive_chat_corpus.v2.json
  -> retained document identities and evaluation policy
comprehensive_chat_gold.v2.jsonl
  -> one uniform semantic expectation per case
reviewed live result JSONL
  -> stage observations and reviewer judgments
scripts/comprehensive-chat-eval.py
  -> deterministic definition/result validation and summary
```

The v2 corpus contains the existing heterogeneous material plus one controlled
same-title, overlapping-version Markdown pair. That pair carries explicit
effective dates and supersession language so version selection, conflict
attribution, and same-title navigation are reviewable without encoding a
benchmark-specific product rule. Lifecycle mutation, retired revisions, and
cross-vault leakage stay in full-chain acceptance.

Every Gold row has the same top-level shape:

| Element | Meaning | Authority |
| --- | --- | --- |
| `scenario` | one primary reading of the case | Gold author |
| `dimensions` | independent retrieval, dialogue, language, authority, and visual coverage | Gold author |
| `history` | parent case or explicit dialogue seed | persisted dialogue contract |
| `runtime` | deterministic injected condition, if any | test harness |
| `expected.terminal` | completed or typed non-semantic failure | runtime contract |
| `expected.decision` | stable mode, source documents, Raw anchors, gap class, source-visual policy, and generation intent | Answer Decision contract |
| `expected.composer` | language, format, core facts, forbidden facts, and asset outcome | Response Composer/public response contract |

Stable document IDs, source-authored Raw anchors, and source-visual caption
anchors may appear in Gold. Request-local support-span IDs, visual references,
composer material IDs, evidence IDs, attachment IDs, paths, hashes, and model
reasons may not.

The deterministic validator checks definition identity, uniform schema,
document and parent references, acyclic dialogue chains, expected mode
combinations, generation intent, source-visual ownership, coverage declarations,
and absence of secrets or private paths. It does not infer semantic correctness
from keywords.

A reviewed live result records observed retrieval, Answer Decision, Response
Composer, evidence, visual, and answer-usability dimensions separately.
Validation rejects missing cases, duplicate executions, malformed stage
observations, unacknowledged hard failures, and aggregate-only reports.
Answer usability determines ordinary acceptance; declared hard failures always
override it. Evidence precision remains independently visible and does not
become a second answer-relevance gate.

Real-provider execution is explicit. The default unit gate validates the corpus,
Gold, and reviewed-result contract without network access, provider credentials,
or user-vault mutation.
