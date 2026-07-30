# ADR 0020: Separate Chat Answer Decision And Composition

## Status

Accepted

## Context

ADR 0019 removed code-owned source routing and physically separate
grounded/general answer paths by assigning one unified final model the whole
semantic answer contract. That model had to judge Raw relevance, select exact
support, select and place source images, decide generated-image intent, choose
Raw/general/gap authority, satisfy citation constraints, and write the final
response in one structured output.

The contract kept authority coherent, but combined two different capabilities:
evidence judgment and natural response composition. Its nested output and
cross-field constraints disproportionately reduced reliability for smaller
models. A malformed presentation choice could also invalidate an otherwise
correct relevance decision.

## Decision

Normal knowledge Chat uses one fixed, non-recursive pipeline:

```text
Retrieval Planner
  -> Query-owned Raw retrieval
  -> Answer Decision
  -> Response Composer
```

Answer Decision is the sole semantic authority for:

- whole-response mode: `raw`, `general`, or `gap`;
- selected current Raw support spans;
- selected same-Raw source visuals;
- an optional unsupported partial gap;
- explicit generated-image intent.

Its strict output contains exactly five fields:

```json
{
  "mode": "raw",
  "spans": ["sp_1_1"],
  "visuals": ["visual_1_1"],
  "gap": null,
  "generate_image": false
}
```

It does not write answer prose, reasons, confidence, language, format,
citations, image positions, or generated-image prompts.

After validating the decision, code groups selections by authoritative Raw
ownership and maps each group to a request-local ID. Response Composer receives
only the selected exact Raw text,
selected visual semantics, the original latest message, dialogue-only history,
the decided mode and gap, and image-generation authorization. It does not
receive unselected evidence, support IDs, Query metadata, paths, offsets, or
durable identities.

Response Composer owns reader-facing wording, structure, latest-message
language, explicit format instructions, partial-gap wording, selected source
visual position, and the generated-image prompt when authorized. It returns
ordered typed text and source-visual items. Every selected material must be
used by text and every selected visual must appear exactly once. It cannot
reconsider relevance or authority.

Code owns schema validation, support and visual authorization, request-local
identity mapping, citation injection, source-image rendering, generated-image
capability enforcement, persistence, retries, cancellation, and typed
retrieval failures. `chat_response.v4` and `chat_session.v4` remain unchanged.

## Consequences

- A normal completed knowledge turn uses three semantic stages, excluding
  bounded retries and an optional image-provider call.
- Smaller models solve two compact contracts instead of one mixed contract.
- Evidence judgment remains singular; the composer cannot add facts from
  unselected local material or silently discard a selected source image.
- General knowledge and knowledge gaps remain explicit model decisions without
  a keyword router or packaged no-match gate.
- Raw remains the factual authority for local answers; decision and composition
  outputs are request-local and never become a new fact store.
- The previous unified-answer prompt and request-local schema are deleted after
  the replacement path is verified.

## Supersession

This ADR supersedes ADR 0019's unified Final Answer model boundary and its
rejection of a dedicated semantic decision stage. ADR 0019's durable
whole-response authority, no keyword routing, code-owned validation, Raw
grounding, and typed terminal-failure principles remain accepted here.

ADR 0012's linear, non-recursive Chat boundary and ADR 0018's Query retrieval
ownership remain unchanged.

## Alternatives Considered

### Keep One Unified Final Answer

Rejected because relevance selection, image intent, structured prose, and
image placement create a large cross-field contract that performs poorly on
smaller models.

### Let Response Composer Reconsider Evidence

Rejected because it creates two answer-authority owners and permits selected
support or visuals to disappear.

### Draft First And Bind Evidence Later

Rejected because unsupported prose would exist before support authorization
and require a semantic correction loop.

### Add A Recursive Agent Loop

Rejected because the product needs a bounded, inspectable pipeline. Existing
gateway retries remain responsible only for malformed stage output.

## Verification

- Candidate and trustworthy no-match turns both report `answer_decision` then
  `response_composer`.
- The decision output has exactly five fields and validates mode, support,
  visual ownership, uniqueness, gap, and image capability.
- Composer input contains only selected request-local materials and no support
  IDs, unselected Raw, paths, offsets, or durable identities.
- Composer output covers every selected material and places every selected
  visual exactly once.
- Public response/session, citations, source images, generated images,
  persistence, streaming, retry, cancellation, and typed retrieval failures
  retain their accepted behavior.
- Structural searches find no live unified Final Answer prompt, schema, or
  `final_answer` semantic phase.

