# 1.10 Wiki Chat Requirements

## Status And Ownership

This accepted v4 revision owns Chat orchestration, answer validation and
finalization, session lifecycle, and persistence. Specification 1.38 owns
model-free retrieval and the evidence it returns. Specification 1.18 owns the
Retrieval Planner and answer-model contracts. Active Raw remains the only local factual
authority.

## Goal

Provide a predictable knowledge-base Chat with one simple mainline:

```text
understand dialogue
  -> read the Query-derived document/chapter outline
  -> select relevant regions and write one regional search expression
  -> retrieve the literal and regional expressions in one shared region group
  -> Answer Decision selects Raw-grounded, general-knowledge, or gap authority
     plus complete non-redundant Raw and source-visual material
  -> Response Composer organizes the locked decision into the final answer
  -> validate citations
  -> persist the turn
```

## Requirements

1. Every knowledge turn preserves the unchanged latest user question as a
   companion expression in every selected Query region group.
2. Chat may invoke one Retrieval Planner before the Query batch.
   The planner may use the complete dialogue projection of user questions and
   final assistant answers plus the locator-only Query-derived document/chapter
   outline.
3. The planner returns only exact region IDs already visible in the outline and
   one standalone search expression per selected region. It may resolve
   follow-up references and translate into the region's derived dominant
   language. A dependent or presentation-only follow-up preserves the latest
   factual subject/source scope unless the user changes it; multi-category and
   comparison requests cover every explicitly requested branch. It cannot
   select a retrieval algorithm, declare evidence or
   no-match, alter vault scope, or answer.
4. Code compiles each selected document or chapter into a typed Query region
   and runs the unchanged question plus the regional expression inside one
   shared region group. Query applies the region's source
   record and source unit membership before ordinary retrieval fusion and
   structural evidence selection; region membership alone cannot create or select
   evidence. Empty, unavailable, or exhausted planning degrades to one
   unscoped unchanged query.
5. Chat accepts Query's evidence result as its input. It does not add a second
   ranking, filtering, truncation, hard context limit, or provider-fit budget.
   Any future evidence-volume policy belongs to Query.
6. Candidate and trustworthy no-match outcomes invoke one Answer Decision
   stage. It receives the original latest message, dialogue-only history,
   typed retrieval outcome, current Raw evidence projection, and advertised
   capabilities. It never receives Retrieval Planner rewrites. It returns only
   `mode`, `spans`, `visuals`, `gap`, and `generated_image_prompt`.
7. Answer Decision is the sole semantic authority for whether the whole
   response is Raw-grounded, general knowledge, or a knowledge gap. In Raw
   mode, each material contains one non-empty set of code-issued support-span
   IDs and zero or more source-visual references owned by that support. Raw
   mode may include one partial gap. General mode contains no material and may
   identify an unsupported remainder. Gap mode contains no material and one
   gap. Mixed factual authority is rejected.
8. After deterministic validation, code replaces selected support and visual
   references with call-local material IDs, one code-owned reader-facing source
   label per material, exact selected Raw text in authoritative source order,
   and selected visual semantics. Response Composer receives only this
   projection plus the original message, a clean dialogue projection, and the
   result of any already completed image generation. It owns language, wording,
   structure, requested format, and the position of every selected source or
   generated visual. It cannot change mode, add material, use an unselected
   visual, or omit a selected visual.
9. Code does not classify local-material wording, image intent, relevance, or
   answer authority. It validates decision shape, support and source-visual
   ownership, complete composer material use, one continuous citation block per
   text item, and one-time selected-visual use after owner text; rejects general
   answers with local citations or visuals and internal material IDs in
   reader-facing prose; derives persisted provenance; and injects public
   citation markers and source-image Markdown.
10. Sessions persist dialogue, identity, provenance, citations, images, compact
   retrieval trace, usage, lifecycle, and Chat-ingest metadata.
11. Sessions do not persist topic anchors, question dimensions, coverage maps,
   candidate frontiers, Raw payloads, Query cursors, or retrieval continuation.
12. Retry reruns the complete turn against current evidence and atomically
   replaces the target turn.
13. Dialogue context contains complete persisted user questions and the
   substantive text of final assistant answers only. Its model projection
   deterministically removes code-rendered citation markers, source/generated
   image Markdown, and generated-image provenance labels. It excludes previous
   evidence records, citation objects, tool traces, and retrieval arguments.
   Dialogue resolves references and presentation requirements but never
   supplies factual support.
14. `generate_image` capability is advertised only when a configured image
   provider is usable. Generated images are presentation artifacts, not factual
   support. Image requests remain on the ordinary Planner, Query, Answer
   Decision, image-provider, and Response Composer mainline. Answer Decision
   alone determines whether the latest intent explicitly requests a newly
   generated image, writes the optional `generated_image_prompt`, and selects
   any relevant source visuals. A source-image request is not permission to
   generate a replacement. Code validates the prompt, runs the provider before
   Response Composer, and gives the composer only request-local generated
   visual semantics and success/failure state. Response Composer places every
   supplied source and generated visual exactly once. Models never receive a
   durable attachment ID, filename, render path, or model-authored attachment
   Markdown.
15. Runtime safety remains responsible for cancellation, wall time, bytes, and
   memory. There is no public `max_turns` Agent-loop control.
16. Session listing reads only summary fields and never materializes turn
   transcripts or tool traces. Legacy v3 trace payloads are compacted in the
   migrated v4 view and remain compact on the next write.
17. Session listing is deterministically ordered and paginated by `offset` and
   `limit`; the response reports total count and continuation so renderer
   surfaces can reach every older session without loading transcripts.
18. Citation preview state belongs to the selected Chat session. Beginning a
   session or vault transition closes the prior preview and invalidates any
   in-flight preview read so a late response cannot populate another session.
19. One public citation marker represents one active Raw source unit. Its
    compact citation record preserves every exact answer-selected range;
    overlapping or touching ranges may collapse, while disjoint ranges MUST
    NOT be widened into one enclosing range. The renderer groups citations by
    source document, reports document and excerpt counts, and highlights every
    selected range while keeping the first range in focus. Opening a citation
    resolves all support text on demand from the identified immutable source
    unit. The transient text is not persisted in the session. A
    source-unit-local range MUST NOT be applied directly to the complete Raw
    document; an unavailable locator opens without a highlight rather than
    guessing another span.

## Compatibility

Chat request, response, retry, and session contracts are v4. One explicit
session v3-to-v4 migration preserves user-visible dialogue, citations,
provenance, images, lifecycle, and ingest metadata while discarding obsolete
control state. New requests do not accept v3.

## Non-Goals

- hidden deep research or iterative planner/read/answer loops;
- wording-, entity-, document-, or benchmark-specific Chat branches;
- Web search or generic shell/browser/filesystem tools;
- changing Query retrieval semantics inside the Chat owner;
- treating prior assistant prose, projections, or generated images as local
  evidence.

## Acceptance

- selected regions produce one combined retrieval batch, one Answer Decision,
  and one Response Composer call for candidate or no-match completion;
- every ordinary completed knowledge turn performs at most one Retrieval
  Planner, one Answer Decision, and one Response Composer semantic stage,
  excluding configured retries and the optional image-provider call;
- follow-ups may resolve through the dialogue-aware Retrieval Planner while
  every region still retains the unchanged question;
- Query alone chooses and combines lexical, atom/claim, entity, and relation
  locators; selected regions are search boundaries, not algorithm modes or
  evidence;
- Query evidence reaches Answer Decision without Chat-owned candidate
  judgment, ranking, winner selection, or best-k limits; unselected evidence
  never reaches Response Composer;
- image wording cannot bypass Query and Answer Decision, and only a validated
  Answer Decision can authorize the image tool;
- explicit source-image requests cannot be satisfied by generation, unknown
  attachment identities, model-authored image Markdown, or asset paths;
  generated images carry a visible non-evidence provenance label;
- grounded, general, gap, retrieval failure, and no-match provenance remain
  distinct without a code-owned semantic source router;
- the Answer Decision schema stays limited to `mode`, `spans`, `visuals`, `gap`,
  and `generated_image_prompt`; selected source visuals and successfully
  generated visuals are mandatory Response Composer inputs and appear exactly
  once in the final answer;
- v3 session migration preserves all user-visible state;
- listing legacy sessions does not load their turn bodies, and migrated traces
  do not retain duplicated Raw payloads;
- every persisted session remains reachable through paginated summaries, and a
  citation preview never survives or races across a session transition;
- citation markers are grouped by Raw source unit while their locator records
  retain every exact disjoint range, group them by document, and preview all
  used spans without admitting unselected retrieval candidates;
- Response Composer can name selected sources from code-owned labels, keeps
  each citation marker adjacent to one continuous supported answer block, and
  places each selected source visual after preceding text has used its owning
  material;
- model-visible history contains substantive dialogue but no code-rendered
  citations or images; Raw, user, dialogue, and visual payloads remain
  untrusted data and cannot override model contracts;
- a complete or partial gap is expressed as a reader-facing limitation rather
  than a bare repetition of the unsupported request fragment;
- structural checks find no live topic-anchor, dimension-coverage,
  retrieval-continuation, recursive planner, `max_turns`, general-routing gate,
  local-evidence regex, or separate general-answer implementation.

## Comprehensive Acceptance Baseline

20. Maintainer acceptance uses one versioned comprehensive Chat corpus isolated
    from the user's default vault. The corpus covers heterogeneous Raw shapes,
    ambiguous source identity, cross-document synthesis, dialogue changes,
    answer authority, language, source visuals, generated-image intent, gaps,
    and typed failures without turning document count into a quality target.
21. Every Gold case declares one scenario plus independent coverage dimensions,
    the latest-message response language, the expected pipeline terminal or
    Answer Decision mode, stable document and Raw-anchor expectations, visual
    policy, generated-image intent, and reader-facing acceptance constraints.
    Request-local span, visual, material, evidence, and attachment IDs are never
    durable Gold authority.
22. Evaluation reports Retrieval, Answer Decision, Response Composer, evidence,
    visual provenance, and answer usability separately. A total score cannot
    hide a hard failure, and evidence precision remains diagnostic when the
    answer is materially correct.
23. Generated-image output without explicit latest-message intent is a hard
    failure. A source-image request never authorizes generation, a selected
    source visual must remain traceable to its Raw owner, and generated images
    never count as evidence.
24. The default deterministic gate validates corpus identity, schema
    uniformity, coverage declarations, Gold references, dialogue graphs, and
    recorded live-run result shape. Real-provider execution remains explicit
    and outside default unit, packaging, and release gates.

The baseline does not add benchmark-specific runtime branches, keywords,
thresholds, prompts, or answer rules. Ingest lifecycle, cross-vault isolation,
source deletion, and stale-index recovery remain owned by their existing
full-chain suites rather than being simulated as ordinary static Chat cases.
