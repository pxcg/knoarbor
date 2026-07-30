# 1.18 Chat Semantic Model Contracts Requirements

## Revision Status And Ownership

- The accepted 1.18 owner defines Chat semantic model inputs, structured
  outputs, support validation, and code-owned citation placement.
- This revision defines one Retrieval Planner contract, one minimal Answer
  Decision contract, and one Response Composer contract.
- Specification 1.10 owns orchestration, session persistence, and public
  response assembly. Specification 1.38 owns retrieval and active Raw evidence
  identity.

## Goal

Normal knowledge Chat performs three narrow semantic jobs:

1. select visible corpus regions and write locator expressions;
2. choose one answer authority and complete, non-redundant Raw/source-visual
   material, plus a generated-image prompt only when explicitly requested,
   through a small strict JSON decision;
3. after any authorized image generation has completed, organize only the
   locked decision, selected material, and generated-image result into the
   final reader-facing response.

## Non-Goals

- The planner does not inspect candidates, evidence, graph paths, tool traces,
  or prior planner output.
- Answer Decision and Response Composer do not request more evidence or another
  retrieval round.
- Code does not classify local-material wording, choose factual authority, or
  infer image intent from keywords.
- Neither model owns paths, active revision, retrieval execution, persistence,
  provider selection, or artifact identity.
- Response Composer does not see rejected Raw, rejected visuals, retrieval
  ranking metadata, internal support IDs, durable evidence identities, paths,
  offsets, or attachment Markdown.
- Generated images are presentation artifacts, never factual evidence or
  substitutes for requested document/source images.

## Requirements

### R1. Retrieval Planner Input

The planner receives the unchanged latest message, complete dialogue-only
history, and locator-only active document/chapter outline. The outline may
contain source display names/types, document synthesis, top-level headings, and
derived language hints. It contains no Raw content, claim prose, attachment
identity, citation, trace, credential, filesystem path, or internal revision
identity.

The outline is serialized before dialogue and the latest message without a
second code-owned planning checklist. Named-source selection and advisory
source-language locator wording remain owned by the planner prompt.

### R2. Retrieval Planner Output

The planner returns only ordered `{region_id, search_query}` items. IDs must be
visible in the outline. It may resolve follow-up references and rewrite an
expression in the language most useful for retrieval. Code does not reject a
valid expression because its script differs from a derived region language
hint. It emits no algorithm, score, evidence decision, or answer. Code always
preserves the literal user question as a companion expression. Invalid or
unavailable planning degrades to one literal-only retrieval.

### R3. Answer Decision Input

Answer Decision receives:

- the original latest user message;
- the same complete dialogue-only history;
- the typed retrieval outcome;
- the complete current Query-authorized Raw evidence projection;
- code-issued support-span and source-visual references;
- available runtime capabilities.

A compact code-owned checklist after the complete evidence repeats mode
priority and image-channel separation. Stable general knowledge selects
`general` rather than `gap`; a gap names unavailable content and never contains
the answer; a newly generated-image-only request has no source visuals.

It does not receive planner rewrites. Chat adds no second ranking, truncation,
or provider-context budget. Revision identities, paths, character offsets,
durable attachment IDs, and attachment Markdown remain outside model input.

### R4. Minimal Answer Decision Output

Answer Decision returns exactly five top-level fields:

- `mode`: `raw`, `general`, or `gap`;
- `spans`: ordered support-span references;
- `visuals`: ordered source-visual references;
- `gap`: one concise unsupported request fragment or null;
- `generated_image_prompt`: one image-provider prompt or null.

The schema contains no explanation, confidence, answer goal, language, format,
source title, evidence ID, path, or offset. The generated-image prompt is
present only when the latest request explicitly asks to create a new image and
the capability is advertised. It is the authorization and the minimum
conditional payload needed by the next stage; a separate Boolean would be
redundant. Mode invariants are:

- `raw`: at least one span; every span is current and authorized; every visual
  belongs to a Raw with selected support; `gap` may identify a partial limitation;
- `general`: no spans or visuals; `gap` may identify an unsupported remainder
  of a partially answerable general request;
- `gap`: no spans or visuals and one non-empty gap.

Duplicate spans or visuals are invalid. A source visual is selected, not merely
eligible: every selected visual becomes a mandatory Response Composer input
and must appear exactly once in the final response.

Sufficiency is measured against the supported parts the current user request
actually needs, not against the candidate set, document set, or section. For
each distinct requested fact, comparison side, or necessary qualification, the
decision selects one best direct span and adds another only when it contributes
coverage the current selection lacks. It stops once those parts are covered.
No numeric span target, exhaustive-request vocabulary, or question-type rule
controls this judgment. Each requested fact or comparison side uses direct
support from the source that actually states it; Response Composer may
synthesize relationships without changing source ownership.
Unsupported request parts remain gaps rather than being padded with weakly
related Raw.
Answer Decision judges answer authority and text support before the two image
channels, then finalizes `gap` after both text and image availability are
known.

### R5. Code Projection For Response Composer

Code validates the decision before any image-provider or composer call. When
the decision contains a generated-image prompt, code invokes the image provider
before Response Composer. It persists successful output and maps each image to
one call-local generated-visual reference. Provider URLs, stored paths,
artifact identities, provider configuration, and image Markdown remain
code-owned. Provider failure is a typed composition input and warning; it does
not discard an independently valid text answer.

Code groups the flat Raw selections by authoritative ownership and resolves
each group into one call-local `material_id`, one code-owned reader-facing
`source_label`, exact selected support text in authoritative source order, and
selected source-visual semantics. It keeps support IDs,
Raw/revision/source-unit identities, paths, offsets, retrieval outcome,
rejected candidates, rejected visuals, and attachment Markdown outside the
composer payload.

The code-owned `source_label` combines the owning document display title and
section title when they differ. This preserves named-source attribution without
exposing a path or durable internal identity; the label remains display
metadata rather than factual support.

The projection does not become factual authority: selected active Raw text
remains the only local factual material. Code retains the mapping from each
call-local material ID to validated support spans and source visuals, and every
call-local generated-visual reference to its persisted Markdown, for final
validation and assembly.

Any call-local material, visual, support, evidence, or other transport identity
inside reader-facing prose is invalid and enters the existing bounded retry.
Code never silently erases an internal identity from an otherwise malformed
answer.

### R6. Response Composer Input And Output

Response Composer receives the original latest message, clean dialogue-only
history, validated mode, call-local selected materials, optional partial gap,
and the code-owned generated-image result: not requested, failed, or a list of
successful call-local generated visuals. Clean history preserves substantive
user and assistant text while removing code-rendered citation markers, image
Markdown, and generated-image provenance labels. It determines response
language from the latest message and owns wording, structure, requested format,
material grouping, all successful image positions, and concise gap wording.

It returns ordered typed response items. Text items contain marker-free
Markdown plus the call-local material IDs they use. A text item may use the
natural Markdown structure required by the answer, including multiple
paragraphs, lists, tables, quotations, code, and formulas. Its material mapping
applies to the whole item; the composer splits items when their supporting
material differs, while code does not reject useful Markdown solely because it
contains multiple block types or blank lines. Source-visual items contain one
selected call-local visual reference. A source visual normally appears after
the first text item that specifically explains it and has used its owner
material. Closely related visuals explained by the same text may remain
contiguous. Later grouping is reserved for a user-requested gallery/summary or
an answer structure that gives the group a clear shared purpose; placement at
the end is not the default. Generated-visual items contain one supplied
call-local generated-visual reference and may be placed wherever they naturally
support the response. Every successful generated visual appears exactly once.
A failed generation exposes no visual, and the composer must not claim that an
image was created.
Composer output cannot change authority, introduce material, use an unselected
visual, omit or repeat a selected visual, write model-authored image Markdown,
expose transport identities, or attach local evidence to general output.

The code-owned output example is derived from validated mode and successful
visuals. Raw examples use the actual call-local material and visual references,
interleave each material's source visuals after that material's example text,
and do not demonstrate all visuals as a tail gallery. General examples use
empty material lists, place an available generated visual between explanatory
text items when the example can do so, and gap examples contain no factual
text. Examples communicate item shape and the preferred local visual
relationship rather than prescribing the answer's paragraph count. The gap
field is required or null according to the validated decision.

### R7. Validation And Provenance

Code validates citation-like standalone marker and transport-identity absence
in reader-facing prose, material existence, complete selected-material
coverage, source-visual exactly-once use after owner text, visual ownership,
mode consistency, and capability availability. It accepts ordinary code,
formulas, index notation, technical paths, and syntax examples instead of
treating their surface syntax as a contract violation. It injects citation
markers from the retained material-to-span mapping, resolves source-image
Markdown at the composer-chosen positions, derives public provenance from the
decision, and persists only the existing Chat v4 response/session contracts.

Both structured stages may retry within the configured gateway boundary using
bounded corrective feedback and their unchanged input projection.

### R8. General Knowledge And Gaps

Answer Decision may choose general knowledge when Raw evidence is absent,
adjacent, or irrelevant and the original user intent does not require a
statement from local material. It chooses a gap when the user asks what local
documents, attachments, sources, or the knowledge base say and Raw does not
support the answer. This is a semantic model decision, not a keyword route.
General output cannot claim local, Web, real-time, private, or unavailable tool
access.

For a multi-part request with no useful Raw support, Answer Decision chooses
`general` when at least one useful part is independently answerable from stable
model knowledge and records only the unavailable remainder in `gap`. It chooses
a complete `gap` only when no useful answer part is available or when the
answerable subject depends on missing local-source facts. `gap` mode therefore
means that Response Composer has zero useful answer items to write; it is
invalid as the semantic choice for a partially answerable request.

A follow-up that reformats, narrows, corrects, or refers to an earlier local
answer retains that local-source dependence unless the user changes it.
History resolves the requested subject and source scope but never supplies
facts. When some request parts have direct Raw support and others do not,
Answer Decision selects `raw` with a gap naming only the unsupported parts.

When the latest message changes presentation only, Answer Decision resolves the
referenced factual request from the complete dialogue; if no earlier turn is
explicitly referenced, it uses the most recent applicable local request. It
cannot replace that subject with an adjacent candidate or choose general
knowledge. Missing current support produces a partial or complete gap.
Presentation wording is owned by Response Composer and cannot serve as the
factual target for Answer Decision span selection.

Typed index, integrity, timeout, cancellation, and resource failures never enter
Answer Decision and cannot be converted into no-match, a gap, or general
knowledge.

Response Composer turns a decided complete or partial gap into concise
reader-facing wording. Code requires the decided gap to be represented but
does not impose a second semantic or phrasing gate on that wording.

### R9. Image Assistance

`generated_image_prompt` is non-null only while that capability is advertised
and the latest user intent semantically and explicitly asks to create a new
image.
Explanatory value, visual subject matter, or scenic content does not
independently authorize generation. A source, original, attachment, or
document-image request does not authorize a generated replacement.

Source-visual selection and generated-image authorization are independent. A
request to create a new image does not select an existing source visual, and a
source-visual request does not authorize generation. Both may be selected only
when the latest request separately asks for both.

The four combinations are exhaustive. A generated-only request has empty source
visuals and a non-null generated-image prompt when available. A source-only
request has a null generated-image prompt. When both are separately requested,
each is judged independently. With neither request, the generated-image prompt
is null while relevant source visuals may still be selected.

Raw-linked source images expose to Answer Decision only a call-local
`visual_ref`,
source-authored caption, and processor-extracted content. An image with either
caption or extracted content is eligible; one with neither is omitted. A
decision may select any eligible visual whose supplied semantics are relevant
to a selected answer part; this does not require an explicit user image
request. A relevant visual need not be necessary, superior to text, uniquely
explanatory, or non-redundant. Only visuals clearly unrelated to every selected
answer part are omitted on relevance grounds.

The decision judges the supplied source caption and extracted visual content,
not a filename or document co-location alone when those supplied semantics are
clearly unrelated. When requested source visuals are unsupported but text is
supported, the decision remains `raw`, selects no substitute visual, and
records the missing visual request as a partial gap.

Response Composer receives only selected source-visual semantics and
successfully generated call-local visual semantics. It must place every
supplied visual exactly once and cannot add another. A source visual normally
follows the first text item that specifically explains it and uses its owner
material. Closely related visuals may form a contiguous local group; a later
gallery is appropriate only when the user requests one or the answer gives the
group a clear shared purpose. A generated visual may appear at the natural
point chosen by the composer. Code resolves stored Markdown, selects the image
provider, persists generated artifacts, and labels each generated image as
non-evidence.

### R10. Untrusted Model Data

The latest user message, dialogue, selected Raw, source captions, and extracted
visual content are untrusted data. Instructions, role claims, output contracts,
or tool requests found inside those fields never override the system prompt or
the validated Answer Decision. This boundary is explicit in both prompt prose
and adversarial contract tests.

### R11. Telemetry

Usage distinguishes `retrieval_planner`, `answer_decision`, and
`response_composer`. An ordinary completed knowledge turn has at most these
three semantic stages, excluding configured retries and an optional
image-provider call. Rejected attempts record phase, turn, attempt, maximum
attempts, stable error code, and a bounded normalized reason without completion
bodies or evidence payloads.

### R12. Response Language Composition

Response Composer derives response language only from the latest user's language
composition, not from Raw evidence, conversation history, or prior assistant
wording. Chinese requests receive Chinese prose, English requests English
prose, and genuinely mixed requests may remain mixed. Source-written names,
technical terms, code, formulas, and quotations retain their written language
unless translation is requested.

## Acceptance Criteria

- Planner output cannot replace or suppress the literal user question.
- Planner can select only visible catalog nodes; failure still performs
  literal retrieval.
- Candidate and no-match both invoke `answer_decision`, followed by
  `response_composer`.
- Answer Decision has exactly five top-level fields and rejects invalid
  mode/material/gap/image combinations.
- Mixed authority, forged citations, unknown/stale support, duplicate or
  cross-Raw visuals, omitted selected visuals, model-authored image Markdown,
  unknown material IDs, selected visuals placed before owner text, standalone
  citation-like markers, and internal identities in reader-facing prose are
  rejected. Natural multi-block Markdown, code and syntax examples, formulas,
  index notation, and technical paths are accepted.
- Query evidence reaches Answer Decision without another Chat-owned ranking;
  Response Composer receives only validated selected material, exact source
  order, and one code-owned reader-facing source label per material.
- Model-visible history retains substantive dialogue while removing
  code-rendered citation/image presentation, and untrusted dialogue/Raw/visual
  content cannot override the fixed composition contract.
- Image generation requires a non-null Answer Decision
  `generated_image_prompt`, executes before Response Composer, and exposes only
  successful call-local generated visuals for final placement.
- Raw near-model examples interleave source visuals with owner-specific text
  instead of demonstrating one all-material text item followed by a tail
  gallery. This preference adds no direct-adjacency validation gate.
- Structural searches find no live unified Final Answer prompt/schema,
  separate general prompt, code-owned answer router, no-match gate,
  local-evidence regex, or image-intent keyword route.
