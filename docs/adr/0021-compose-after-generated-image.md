# ADR 0021: Compose After Generated-Image Execution

## Status

Accepted

## Context

ADR 0020 separated semantic answer judgment from final response composition.
It assigned generated-image intent to Answer Decision but left prompt writing
with Response Composer. Code therefore had to finish composition, invoke the
image provider afterward, and append every successful image at the end of the
answer.

That order prevents the final composition model from seeing or positioning the
generated artifact. It also gives generated images a code-owned presentation
path separate from source-image placement.

## Decision

Normal knowledge Chat uses this fixed, non-recursive order:

```text
Retrieval Planner
  -> Query-owned Raw retrieval
  -> Answer Decision
  -> optional generated-image provider call
  -> Response Composer
```

Answer Decision retains exactly five output fields, but its fifth field becomes
`generated_image_prompt: string | null` instead of the redundant
`generate_image: boolean`. A non-null prompt is valid only for explicit
create-new intent and advertised provider capability. It both authorizes the
provider call and supplies the only conditional payload that call requires.

Code validates the decision, invokes the provider, persists successful output,
and maps each image to a request-local generated-visual reference. Response
Composer receives only those references and safe semantic descriptions, plus a
typed `not_requested`, `failed`, or `available` status. It never receives
provider URLs, filesystem paths, artifact identities, or image Markdown.

Response Composer returns ordered text, selected source-visual, and successful
generated-visual items. It places every supplied visual exactly once. Source
visuals still follow text using their owning Raw material. Generated visuals
may appear wherever they naturally support the response and never count as
evidence.

Code renders each generated visual at the selected item position with a visible
non-evidence label. Provider failure preserves an independently valid text
answer, exposes no generated visual, and retains code-owned cleanup and warning
behavior.

## Consequences

- The third semantic model becomes the single final presentation owner for
  text, source images, and generated images.
- The post-composition generated-image append path is deleted.
- Answer Decision gains one conditional prompt-writing responsibility but no
  extra top-level field or answer prose.
- No fourth semantic model, recursive loop, public Chat schema, persisted
  session migration, provider-config change, or artifact-layout change is
  introduced.
- Generated images remain presentation artifacts and cannot establish or
  replace Raw support.

## Supersession

This ADR supersedes only ADR 0020's generated-image prompt ownership and
post-composition provider order. ADR 0020's separate Answer Decision and
Response Composer stages, whole-response authority, selected Raw/source-visual
ownership, and code-owned validation remain accepted.

## Alternatives Considered

### Keep Post-Composition Generation

Rejected because generated images can only be appended after the completed
answer and cannot participate in final layout.

### Keep A Boolean And Add A Prompt Field

Rejected because the Boolean duplicates whether the conditional prompt is
present and increases the small-model JSON contract.

### Add A Fourth Prompt-Writing Model

Rejected because it adds latency and another semantic boundary while Answer
Decision already sees explicit image intent and selected support.

### Let Code Write The Prompt

Rejected because deterministic code would have to reinterpret user semantics
and selected facts that are already owned by Answer Decision.

## Verification

- Decision validation requires exactly five fields and rejects unavailable or
  unsafe generated-image prompts.
- Provider execution occurs after `answer_decision` and before
  `response_composer`.
- Composer input contains request-local generated-visual semantics but no
  provider URL, stored path, manifest path, or Markdown.
- Composer validation rejects unknown, missing, or repeated successful
  generated visuals.
- Provider failure still composes the valid text response and records the
  existing warning.
- Generated image Markdown and its non-evidence label render at the
  composer-selected item position.

