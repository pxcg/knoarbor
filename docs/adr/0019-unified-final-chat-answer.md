# ADR 0019: Unified Final Chat Answer

## Status

Superseded

## Context

The ordinary Chat path already uses one Retrieval Planner and one Query-owned
Raw retrieval batch. Its answer layer nevertheless retained two semantic
synthesizers and a code-owned source router:

1. a grounded answer call inspected candidate Raw evidence;
2. code classified the result with keyword rules and a packaged no-match gate;
3. a separate general answer call could run after grounded support was absent.

This made an ordinary turn use up to three semantic model stages. It also made
code decide a semantic question—whether the user's original request should be
answered from local material, general knowledge, or as a local knowledge
gap—using wording patterns and retrieval state. Low-capability models faced two
different answer schemas, including optional nested image fields that could
invalidate otherwise usable text.

## Decision

Normal KnoArbor Chat has two semantic stages:

```text
Retrieval Planner
  -> Query-owned Raw retrieval
  -> Unified Final Answer
```

Retries of either stage and an optional image-provider call are not additional
semantic stages.

The Retrieval Planner receives the latest question, dialogue-only history, and
the active document/section outline. It selects regions and writes locator
expressions. Those rewrites are not passed to the Final Answer model.

The Unified Final Answer model receives:

- the original latest user message;
- dialogue-only history;
- the typed retrieval outcome;
- the current Raw evidence projection, including code-issued support-span and
  source-visual references;
- available runtime capabilities.

It chooses exactly one answer authority for the whole response:

- **Raw-grounded:** every answer block selects non-empty support-span IDs;
- **general knowledge:** every answer block selects no support spans and no
  source visuals;
- **knowledge gap:** no answer blocks, with a concise gap.

Mixed grounded and general blocks are rejected until a public block-level
provenance contract is deliberately introduced. Grounded blocks may include an
explicit gap for unsupported parts.

Code does not semantically route answer authority. It validates:

- support IDs are current and authorized;
- standalone source-visual placeholders belong to the same selected Raw
  evidence and model-authored image Markdown or paths are invalid;
- general answers contain no local citation markers, identities, or visuals;
- one response does not mix factual authorities;
- generated-image intent is used only when that capability is available.

Code then derives persisted provenance from validated support selection,
injects citations, replaces validated source-visual placeholders with stored
Markdown at their selected paragraph positions, optionally calls the configured
image provider, and persists the turn.

Generated-image intent is one optional string,
`generated_image_prompt`. The Final Answer model emits it only when the latest
user intent semantically and explicitly asks to create a new image. Code does
not use image-intent keyword routing. Malformed optional image intent is
ignored when the core answer remains valid; core answer and support fields
remain strict.

Greeting, help, and vault-inventory product capabilities may remain
deterministic shortcuts. Retrieval failures, cancellation, and resource
exhaustion remain typed code-owned terminals and may end before Final Answer.

## Consequences

- A normal completed knowledge turn uses at most two semantic stages.
- Candidate evidence, true no-match, and weak adjacent evidence all reach the
  same final semantic decision.
- The model answers the original user intent instead of a retrieval rewrite.
- General knowledge cannot be presented with local citations or source images.
- Local-source questions can return a model-authored knowledge gap without a
  keyword classifier or deterministic replacement prose.
- One answer prompt and one output schema reduce retry pressure for smaller
  models.
- The packaged no-match quality gate, explicit local-evidence regex, separate
  general prompt, and separate grounded/general synthesizer classes are
  deleted.

## Supersession

ADR 0020 supersedes this ADR's unified Final Answer model boundary and its
rejection of a dedicated semantic decision stage. The whole-response authority,
no keyword routing, Raw grounding, code-owned validation, and typed terminal
failure principles continue in ADR 0020.

This ADR supersedes ADR 0010's code-owned automatic source router and ADR
0006's requirement for physically separate grounded and general answer
prompts. Source provenance remains mandatory, but it is represented by
validated support selection and persisted answer mode.

This ADR supersedes ADR 0012 only where that decision assigned source routing
to code and described separate grounded/general answer stages. ADR 0012's
linear single-batch Chat boundary remains accepted.

## Alternatives Considered

### Keep The Third General Call

Rejected because the grounded call was already performing the semantic
relevance judgment, and the extra prompt duplicated answer work and failure
surface.

### Add A Dedicated Routing Model

Rejected because it would add another semantic stage and require a second
contract without improving evidence authority.

### Keep Keyword Routing For Local Questions And Images

Rejected because isolated phrases cannot reliably represent conversational
intent and would recreate case-specific routing rules.

### Allow Mixed Grounded And General Blocks Immediately

Deferred because correct rendering, persistence, and reader-visible provenance
would require a new block-level public contract.

## Verification

- Candidate and no-match tests both invoke the same `final_answer` phase.
- Normal knowledge turns report at most the `retrieval_planner` and
  `final_answer` semantic phases.
- Grounded, general, partial, and gap drafts are accepted through one schema.
- Mixed authority, forged citations, unknown support IDs, and cross-Raw source
  visuals are rejected.
- Image generation occurs only from a validated model-authored
  `generated_image_prompt`; image wording never bypasses Final Answer.
- Searches find no live general-routing gate, local-evidence regex, separate
  general prompt, or grounded/general synthesizer.
