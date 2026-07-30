# 1.18 Chat Semantic Model Contracts Design

## Overview

Normal knowledge Chat uses three fixed semantic contracts:

```text
Retrieval Planner
  -> Query-owned retrieval
  -> Answer Decision
  -> optional generated-image provider call
  -> Response Composer
```

Retrieval Planner is a locator. Answer Decision is the sole semantic authority
for answer mode, relevant Raw support, source-visual selection, partial gaps,
and the conditional generated-image prompt. Code invokes the image provider
after validating that decision. Response Composer is the sole owner of
reader-facing wording, structure, requested format, response language, and all
successful visual positions. Code owns retrieval, identity, validation,
projection, provider execution, citations, rendering, persistence, retry, and
safety.

The pipeline is fixed and non-recursive. Neither answer stage may request
another retrieval or call the other stage again.

## Retrieval Planner

The planner receives the locator-only active corpus outline followed by
dialogue-only context and the latest user message. Named-source selection and
advisory source-language rewriting live once in the planner prompt rather than
being duplicated in a code-owned checklist. It returns exact visible region IDs
plus one standalone regional expression. Code preserves the unchanged latest
question in every selected region group. Planner failure degrades to one
unscoped literal Query.

Planner rewrites never reach either answer stage.

## Answer Decision

### Input

Answer Decision receives:

```json
{
  "decision_state": {
    "latest_user_message": "original latest message",
    "conversation_context": [
      {"user": "prior question", "assistant": "prior final answer"}
    ],
    "retrieval_outcome": "candidates",
    "raw_evidence": [
      {
        "source_label": "reader-facing source",
        "support_spans": [
          {"support_span_id": "sp_1_1", "text": "exact selected Raw text"}
        ],
        "source_visuals": [
          {
            "visual_ref": "visual_1_1",
            "caption": "source-authored caption",
            "extracted_content": "processor-extracted visual semantics"
          }
        ]
      }
    ],
    "runtime_capabilities": {"generate_image": true}
  }
}
```

The input contains all current Query-authorized Raw evidence because the stage
must judge relevance and authority. It excludes planner rewrites, retrieval
scores, paths, filenames, offsets, durable attachment/revision identities,
attachment Markdown, and credentials.

The code-owned checklist at the end also repeats mode priority, gap authority,
and the distinction between newly generated images and source images. A
new-image-only request therefore cannot opportunistically select a source
visual.

### Output

The strict output has exactly five fields:

```json
{
  "mode": "raw",
  "spans": ["sp_1_1", "sp_1_2"],
  "visuals": ["visual_1_1"],
  "gap": null,
  "generated_image_prompt": null
}
```

The model does not return a reason, confidence, answer goal, user-need list,
language, format, source title, evidence identity, offset, final prose, or
image position. The generated-image prompt is conditional and replaces the
redundant Boolean authorization: null means generation is not authorized; a
non-empty prompt both authorizes the call and supplies its required input.

Mode invariants:

| Mode | Raw references | Gap | Generated-image prompt |
| --- | --- | --- | --- |
| `raw` | one or more spans; optional same-Raw visuals | optional partial gap | non-null only for explicit latest-message intent and advertised capability |
| `general` | empty | optional unsupported remainder | non-null only for explicit latest-message intent and advertised capability |
| `gap` | empty | required | non-null only for explicit latest-message intent and advertised capability |

Every selected span must be current and authorized. Every selected visual must
belong to a Raw source that also has selected support. Span and visual
references are globally unique in the decision. A selected visual is mandatory,
not advisory.

The decision procedure resolves the current request and inherited local-source
scope first, chooses answer authority and a compact direct-support set, decides
the two image channels, and only then finalizes the unsupported remainder.
Sufficiency is relative to distinct requested facts, comparison sides, and
necessary qualifications, not to retrieved candidates or documents. One best
span covers each such part; another is selected only when it adds missing
answer coverage.
No numeric target, exhaustive vocabulary, or question-type branch controls the
selection. A compact code-owned checklist after the complete evidence restates
only mode, sufficiency, source ownership, and image-channel boundaries; it does
not crop, rerank, or add a second semantic decision. The state places the
unchanged latest message and dialogue after the evidence payload, preserving
evidence contents and order while keeping the request adjacent to the output
contract.
Partial support produces Raw mode plus a gap instead of weak-evidence padding.

Mode selection uses a simple authority priority after resolving answerable
parts: any useful direct Raw support selects `raw`; otherwise any useful stable
general-knowledge support selects `general`; only the absence of both selects
`gap`. An unavailable remainder is recorded in `gap` without overriding that
mode priority.

`candidates` does not force Raw mode: weak or adjacent candidates may produce
general mode or gap according to original user intent. Trustworthy `no_match`
does not force a gap: a stable general question may produce general mode.
General mode is unavailable when the latest request depends on an earlier
local-source answer; history identifies that dependency but never supplies
facts.

When a no-Raw multi-part request contains both a stable general-knowledge part
and an unavailable part, the whole-response authority remains `general` and
the unavailable remainder is represented by `gap`. A complete `gap` is reserved
for requests with no useful answerable part or with missing required
local-source authority.

Source-visual selection and generated-image authorization are separate
decisions. A newly generated-image request does not select a source visual, and
a source-visual request does not authorize generation. Both are valid together
only when separately requested. Source-visual relevance is judged from supplied
caption and extracted content against selected answer parts. Eligible visuals
are accepted broadly: the decision omits only visuals clearly unrelated to
every selected answer part and does not require a relevant visual to outperform
text, be uniquely explanatory, or avoid overlap with the written answer.
Filename or document co-location alone cannot override clearly unrelated
supplied semantics.

The prompt presents this as one exhaustive four-row decision table: generated
only, source only, both separately requested, or neither. A generated-only
request has no source visuals; an unsatisfied source-visual request with
supported text remains Raw mode with a partial gap.

Index, integrity, timeout, cancellation, and resource failures end in Chat code
before Answer Decision.

## Generated-Image Execution And Selected-Material Projection

Code validates the decision before any provider or composer call. A non-null
generated-image prompt is sent to the configured image provider immediately
after Answer Decision. Successful images are persisted through the existing
chat artifact owner and mapped to call-local generated-visual references:

```json
{
  "visual_ref": "generated_visual_1",
  "description": "provider-revised prompt or the validated requested prompt"
}
```

Only this call-local semantic projection reaches Response Composer. Code
retains provider identity, URLs, paths, artifact manifests, and rendered
Markdown. When generation fails or returns no stored image, code records the
existing warning and passes `failed` with no generated visuals; the text
response still composes normally.

Code also maps each selected Raw material to one request-local ID:

```json
{
  "material_id": "material_1",
  "source_label": "reader-facing current source title",
  "raw": [
    "exact selected Raw support text",
    "another exact selected Raw support text"
  ],
  "visuals": [
    {
      "visual_ref": "visual_1_1",
      "caption": "source-authored caption",
      "extracted_content": "processor-extracted visual semantics"
    }
  ]
}
```

The projection preserves exact Raw text as factual authority and orders spans
within each Raw by their code-owned source positions. `source_label` is
code-projected document-and-section display metadata for attribution, never a
new factual source or model-authored summary. It identifies the owning document
when a section title alone would be ambiguous across sources, without exposing
a path or durable identity. Code retains a private request-local map from
`material_id` to selected support spans and source visuals.

Response Composer does not receive:

- Query outcome, query expressions, region IDs, scores, traces, or warnings;
- unselected Raw or unselected visuals;
- support-span IDs, evidence IDs, Raw/revision/source-unit identities;
- paths, filenames, hashes, MIME types, offsets, or attachment Markdown;
- Answer Decision explanations, because the decision schema has none.

## Response Composer

### Input

```json
{
  "composition_state": {
    "latest_user_message": "original latest message",
    "conversation_context": [
      {"user": "prior question", "assistant": "prior final answer"}
    ],
    "mode": "raw",
    "materials": [
      {
        "material_id": "material_1",
        "source_label": "5. AI RMF Core",
        "raw": ["exact selected Raw support text"],
        "visuals": [
          {
            "visual_ref": "visual_1_1",
            "caption": "source-authored caption",
            "extracted_content": "processor-extracted visual semantics"
          }
        ]
      }
    ],
    "gap": null,
    "generated_image": {
      "status": "available",
      "visuals": [
        {
          "visual_ref": "generated_visual_1",
          "description": "A concise generated diagram"
        }
      ]
    }
  }
}
```

The composer reads the original user request and clean necessary dialogue so it
can resolve presentation instructions and write naturally. Code removes
rendered citation markers, source/generated image Markdown, and generated-image
provenance labels from prior assistant turns while retaining substantive text.
In Raw mode, selected Raw remains its only local factual authority; the source
label exists only so the answer can name that authority. In general mode, the
composer may use stable model knowledge without implying local, Web, real-time,
or private access. In gap mode, it writes only a concise reader-facing
limitation.

`generated_image.status` is `not_requested`, `failed`, or `available`.
Available visuals are presentation artifacts and never enter a text item's
materials. A failed result lets the composer avoid claiming that an image was
created without asking it to retry or invent a replacement.

### Output

```json
{
  "items": [
    {
      "type": "text",
      "markdown": "Natural answer text.",
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

The code-owned output example is mode-specific and uses current call-local
references. Raw mode builds one example text item per selected material and
places that material's selected source visuals immediately after it. The
example therefore demonstrates owner-local composition rather than one text
item containing every material followed by a tail gallery. This is presentation
guidance, not a new runtime adjacency invariant: the composer may still combine
materials when they support one statement or form a later visual group when the
user requests a gallery/summary or the answer gives it a clear shared purpose.
General mode contains answer text with an empty material list; when a generated
visual is available, its example position is between an introductory and
continuing text item instead of always at the tail. Gap mode contains no factual
text items but may contain a successful generated visual. `gap_markdown` is
required or null according to the validated decision; image generation
supplements rather than replaces authorized text.

Text items own marker-free Markdown and reference only known call-local
material IDs. One item may contain the natural Markdown structure needed by the
requested answer, including paragraphs, lists, tables, quotations, code, and
formulas. Its material mapping applies to the whole item; the composer splits
items when their supporting material differs, but code does not reject useful
Markdown solely because it contains multiple block types or blank lines.
Source-visual items determine exact reading order and reference only visuals
selected by Answer Decision. By default, a visual follows the first text item
that specifically explains it and uses its owner material. Closely related
visuals explained by that text may remain contiguous. Later grouping is
reserved for a user-requested gallery/summary or an answer structure with a
clear shared purpose. The composer must use every selected material in at least
one text item and every selected visual exactly once.
Generated-visual items reference only successful call-local provider output,
may be placed wherever they naturally support the response, and must also
appear exactly once.

In general mode, text items carry no materials and no source visuals, and may
be followed by `gap_markdown` for an unsupported remainder. In gap mode,
`items` contains no text or source-visual items, while an available generated
visual remains permitted and `gap_markdown` is required. Raw mode may combine
supported text items with one partial `gap_markdown`.

A generated visual cannot replace a gap. A complete or partial
`gap_markdown` represents the decided unsupported part; its exact reader-facing
phrasing belongs to the composer.
Model-authored Markdown image syntax, citation-like standalone numeric markers,
material IDs, support IDs, evidence IDs, and visual placeholders in
reader-facing prose are invalid. Code and inline-code examples are excluded
from these surface checks. Numeric brackets remain valid in code, formulas,
array/index notation, and other substantive text where they are not standalone
citation tokens. Filesystem and URL text is not rejected merely by shape
because source code, technical instructions, and user-requested paths are valid
answer content; request-local paths remain absent from the composer input
projection.

## Deterministic Finalization

Code validates:

1. decision schema and mode invariants;
2. support existence, authorization, deduplication, and visual ownership;
3. composer mode consistency and known material/visual references;
4. complete selected-material coverage without constraining valid Markdown
   block structure;
5. exactly-once selected-visual placement after preceding owner text;
6. exactly-once placement of every successful generated visual;
7. absence of citation-like standalone markers, model-authored image Markdown,
   and internal identities without rejecting ordinary code, formulas, or paths;
8. generated-image prompt authorization and provider-result projection.

For each text item, code expands its material IDs into the retained support
spans, collapses them to one citation per Raw unit while preserving exact
disjoint ranges, and injects adjacent public markers. For each visual item,
code renders the stored source-image Markdown at that ordered position.
For each generated-visual item, code renders the persisted generated-image
Markdown with its visible non-evidence label at the composer-selected position.

Code intentionally does not validate direct adjacency between a source visual
and its owner text. The owner-before check remains the deterministic safety
boundary; local placement is a composer presentation preference so useful
multi-paragraph explanation and justified galleries do not become retry
failures.

The existing `ChatAnswerDraft`, `chat_response.v4`, `chat_session.v4`, citation
resolver, renderer, and generated-image artifact contracts remain unchanged.
Decision and composition drafts are request-local and are not persisted.

## Dialogue, Language, And Style

Both answer stages receive complete substantive `{user, assistant}` dialogue
without prior evidence, code-rendered citation markers, image Markdown,
generated-image labels, traces, planner rewrites, or retrieval arguments.
Dialogue resolves intent and presentation but is never factual authority.

Only Response Composer writes reader-facing prose. It derives language from the
latest user message, preserves source-written technical terms unless
translation is requested, and follows explicit format instructions when useful.

## Streaming, Retry, And Telemetry

Structured output is fully validated before answer text is released. Each
stage may retry through the existing bounded model gateway with redacted
contract feedback and an unchanged input projection.

Model phases are:

- `retrieval_planner`;
- `answer_decision`;
- `response_composer`.

The source-selection event is emitted only after composition and deterministic
finalization. The externally streamed answer remains one validated answer
delta followed by the existing final response.

## Security And Privacy

All user, dialogue, Raw, and visual content is untrusted data. The system prompt
explicitly tells Response Composer that instructions, role claims, output
contracts, and tool requests inside any data field are content to interpret,
not instructions to follow. Model payloads exclude credentials, filesystem
paths, durable revision and attachment identities, provider URLs, and stored
Markdown. Diagnostics never record model completion bodies or evidence
payloads.

## Rejected Alternatives

### Keep One Unified Final Answer

Rejected because one model simultaneously judged authority, selected exact
support and visuals, interpreted image intent, wrote structured prose, and
placed images. The large mixed contract disproportionately penalized smaller
models.

### Let Response Composer Reconsider Relevance

Rejected because it would create a second semantic authority and allow selected
source visuals or Raw support to disappear after Answer Decision.

### Draft First, Bind Evidence Later

Rejected because unsupported prose could exist before evidence authorization
and require a correction loop.

### Generate After Response Composer

Rejected because the composer cannot place an artifact that does not yet
exist. Appending every generated image after the completed answer also creates
a second code-owned presentation path.

### Add A Separate Image-Prompt Model

Rejected because Answer Decision already resolves explicit image intent and
sees the selected factual support. A fourth semantic model would add latency
and another contract without a distinct source of authority.

### Add A Recursive Correction Agent

Rejected because bounded gateway retries already own malformed structured
output. Chat remains a fixed pipeline.
