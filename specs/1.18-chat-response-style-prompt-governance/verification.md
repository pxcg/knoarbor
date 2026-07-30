# 1.18 Chat Semantic Model Contracts Verification

## Focused Tests

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_chat_agent \
  tests.test_chat_tool_flows \
  tests.test_chat_support_spans \
  tests.test_chat_stream \
  tests.test_chat_sessions \
  tests.test_semantic_contracts
```

## Required Assertions

- Retrieval Planner receives the original question, dialogue-only history, and
  locator-only outline.
- Planner output contains only visible region IDs and regional expressions.
- Named-source cases keep the unchanged latest request after the outline,
  select the named source rather than a similar-topic document, and may use
  source-language locator wording when it improves recall.
- Planner input has no duplicated code-owned planning checklist.
- Code preserves the literal question in every selected region group.
- Planner failure degrades to one literal-only Query batch.
- Answer Decision receives the original question, dialogue-only history, typed
  retrieval outcome, complete current Query evidence, visual semantics, and
  advertised runtime capabilities.
- Answer Decision input contains no planner rewrites, filesystem paths, durable
  attachment IDs, offsets, scores, or prior-turn evidence.
- Candidate and trustworthy no-match both invoke `answer_decision` followed by
  `response_composer`.
- A normal completed knowledge turn reports at most
  `retrieval_planner`, `answer_decision`, and `response_composer`, excluding
  retries and the image provider.
- The five-field decision schema accepts Raw, general, partial-gap, gap-only,
  and explicitly requested generated-image prompts and rejects a redundant
  Boolean authorization or extra model-authored planning fields.
- Stable general-knowledge cases choose `general`, gap wording never supplies
  the answer, and new-image-only requests do not select source visuals.
- Answer Decision treats adjacent, background, premise-only, duplicate,
  already-covered, and merely co-located spans as unselected; each additional
  selected span adds a distinct requested fact, comparison side, or necessary
  qualification. Removing irrelevant candidates or changing candidate order
  does not expand the semantic selection.
- Prompt and runtime input contain no numeric span target, exhaustive-request
  vocabulary, or question-type branch. Every requested fact or comparison side
  retains direct support from its actual source.
- Long evidence packets retain the complete Query-authorized input and repeat
  the compact code-owned selection checklist after it; the checklist does not
  crop, reorder, or semantically rank Raw.
- The unchanged latest message and dialogue follow the complete evidence
  payload, keeping the actual request adjacent to the checklist without
  changing Raw order.
- Partially supported multi-part requests produce Raw mode with an unsupported
  fragment instead of weak-evidence padding.
- A follow-up that depends on an earlier local-source answer never routes to
  general knowledge solely because current Raw is missing.
- Presentation-only follow-ups resolve explicit references across complete
  dialogue, otherwise use the most recent applicable factual request, retain
  its source scope, reject adjacent-topic substitution, and use a gap for any
  part current Raw cannot re-support.
- Unknown or unauthorized support IDs, repeated support or visuals,
  cross-Raw visuals, invalid mode fields, unsafe generated-image prompts, and
  unavailable image generation are rejected before provider execution.
- Composer input uses mode-specific examples: Raw interleaves each material's
  actual selected source-visual references after owner-specific example text,
  general uses empty material lists and does not always demonstrate an
  available generated visual at the tail, and gap has no factual text. It
  receives the typed generated-image result and never treats a generated visual
  as source evidence or as a replacement for authorized text.
- Response Composer receives only call-local selected materials with exact Raw
  text in source order, one code-owned reader-facing document-and-section
  source label, selected source-visual semantics, and successful generated-
  visual semantics; it receives no support IDs, unselected Raw, retrieval
  outcome, provider URLs, paths, offsets, or durable identities.
- Named cross-document cases preserve owning-document attribution even when
  section titles alone do not identify the document.
- Unknown materials, incomplete material coverage, missing/repeated selected
  visuals, visuals placed before owner text, standalone citation-like markers,
  model-authored image Markdown, and internal identities in reader-facing prose
  are rejected.
- Multi-paragraph Markdown, mixed paragraph/list/table structure, fenced and
  inline code (including syntax examples that resemble transport identities or
  image Markdown), formulas, array/index notation, and technical filesystem or
  API paths remain valid answer content.
- Code derives Raw/general/gap provenance from the validated decision and
  injects citations only for Raw mode.
- Dialogue history includes complete substantive prior user/final-assistant
  text but no evidence, code-rendered citation markers, source/generated image
  Markdown, generated-image labels, trace, or retrieval arguments.
- Instructions or role/output/tool claims embedded in user, dialogue, Raw,
  caption, or extracted visual content remain untrusted data and do not
  override the composer contract.
- Chinese, English, and genuinely mixed-language requests preserve their
  composition and source-written technical terms.
- Image wording never bypasses Answer Decision.
- Source-image selection and generated-image authorization cover all four
  combinations: neither, source only, generated only, and both explicitly
  requested. Neither channel substitutes for the other.
- Images with either a source caption or processor-extracted content remain
  eligible. The decision prompt and runtime checklist allow any eligible visual
  relevant to a selected answer part, omit clearly unrelated visuals, and do
  not require a relevant visual to outperform text or be uniquely explanatory.
- Answer Decision returns `generated_image_prompt` exactly when explicit
  generation is requested and capability is available; the provider executes
  before Response Composer.
- Every selected source image is rendered exactly once after preceding text has
  used its owning material. Focused examples demonstrate local placement after
  the first specific owner explanation, while a separately tested justified
  later group remains valid without a direct-adjacency gate. Every successful
  generated visual is placed exactly once by Response Composer and carries a
  visible non-evidence label at that position.
- Failed or empty generation still invokes Response Composer with a typed
  failure, preserves the independently valid text answer, emits no generated-
  visual item, and retains the existing warning/cleanup behavior.
- Structural search finds no composer-owned generated-image prompt and no
  post-composition generated-image append path.
- Source events are final (`provisional: false`) and agree with persisted
  provenance.

## Structural Residual Check

Live source, tests, and active specifications contain no implementation owner
for:

```text
ChatGroundedAnswerSynthesizer
ChatGeneralAnswerSynthesizer
ChatGroundedAnswerDraft
ChatGeneralAnswerDraft
wiki_chat_general_answer.md
wiki_chat_answer.md
ChatFinalAnswerDraft
general_routing_enabled
general_routing_gate_passed
question_requires_local_evidence
route_chat_answer
grounded_answer
general_answer
final_answer
```

Historical ADR text may retain superseded terms.

## Governance

Run formatting/lint, affected backend tests, documentation governance and link
checks, architectural tests, and the simplification parity review. Desktop
packaging and real-provider acceptance remain separate release checkpoints.
