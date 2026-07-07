# 1.18 Chat Response Style And Prompt Governance Requirements

## Problem

KnoArbor Chat has a strong wiki-first retrieval and evidence pipeline, but its
answer prompt is mostly a RAG contract. It tells the model how to use evidence,
citations, attachments, and generated images, but it does not yet define a
product-level response style that matches enterprise local-knowledge usage.

At the same time, prompt instructions for retrieval, evidence, tool planning,
image generation, and attachment rendering have grown organically. Some rules
are repeated across the planner, evidence pack, and answer prompt, and at least
one answer-stage instruction describes a tool action the answer synthesizer
cannot perform. Prompt governance needs a first-class SDD boundary before more
chat behavior is added.

## Goals

- Add a simple answer-depth preference for Chat responses.
- Expose the preference in Settings > General as a compact segmented control.
- Keep the preference local to answer expression: wording, density, and
  structure.
- Treat the preference as a default style, not an override of the latest user
  instruction. Explicit requests such as "briefly", "详细展开", or "只给结论"
  take precedence for that turn.
- Prevent response style from changing retrieval, evidence sufficiency, tool
  availability, citation rules, or image-generation permissions.
- Define KnoArbor's default response voice as professional, direct,
  evidence-grounded, and natural in the user's language.
- Tighten prompt boundaries for retrieval, evidence, tool planning, generated
  images, and existing attachment images.
- Remove or rewrite prompt text that asks a non-tool answer synthesizer to call
  tools.
- Make prompt governance fixes at least as important as the Settings UI, because
  incorrect layer ownership can cause wrong behavior even when the style control
  is absent.
- Treat wiki pages, source text, attachment metadata, OCR, and evidence payloads
  as data, not instructions that can alter system, developer, or tool policy.
- Keep enterprise data-governance boundaries visible when image generation uses
  knowledge-base evidence: generation must be explicit and based on the minimum
  necessary visual prompt.
- Avoid claiming visual inspection of attachment pixels unless a future vision
  tool or explicit image-analysis evidence is present.
- Keep prompt layering inspectable and testable from backend unit tests.
- Preserve the existing chat architecture: planner chooses tools, code-owned
  retrieval policy guards tool choices, answer synthesis writes user-facing
  Markdown from tool observations.

## Non-Goals

- Do not add a free-form custom system prompt editor.
- Do not add personality presets such as friendly, academic, playful, or sales.
- Do not let users disable citations, evidence checks, or tool guardrails
  through style settings.
- Do not use response style to tune search mode, max results, token budget, or
  model temperature.
- Do not expose prompt implementation details in normal product UI.
- Do not rewrite the chat agent as native provider tool calling.
- Do not make image generation automatic from generic visual wording; explicit
  creation intent remains required.
- Do not add general image understanding or OCR in this feature.
- Do not make response style a data-loss-prevention or external-provider policy
  control.
- Do not add backward-compatibility shims for unused development-stage config
  shapes.

## User Scenarios

### Choose A Default Answer Depth

As an enterprise user, I can choose whether Chat answers are concise, balanced,
or deep without editing prompt files.

Acceptance criteria:

- Settings > General shows an answer-depth control with three choices:
  concise, balanced, and deep.
- The selected value is saved to `chat.response_style`.
- Reopening Settings shows the saved value.
- The default is balanced when the config does not specify a value.
- Invalid values are rejected by config validation.

### Ask A Quick Knowledge Question

As a user who prefers concise answers, I can ask a direct question and receive a
short answer that still remains grounded in the selected wiki evidence.

Acceptance criteria:

- Concise style starts with the answer and avoids unnecessary sections.
- Citations still appear when wiki evidence is used and useful.
- Evidence gaps are still stated when local evidence is weak.
- The service does not reduce retrieval or skip required evidence because the
  style is concise.
- If the user asks for detail in the latest turn, concise style still expands
  enough to satisfy that explicit request.

### Ask For Architecture Or Design Detail

As a user working through a design question, I can use deep style to get more
complete synthesis, tradeoffs, and next steps.

Acceptance criteria:

- Deep style expands mechanisms, boundaries, tradeoffs, examples, and next
  steps when evidence supports them.
- Deep style does not invent unsupported details to fill length.
- For Chinese user messages, the answer uses natural professional Chinese while
  preserving standard English technical terms when clearer.
- If the user asks for a brief answer in the latest turn, deep style yields a
  short but still well-grounded answer.

### Render Existing Attachment Images

As a user asking about an image already present in a wiki page or source, I can
receive the relevant existing image in the answer without triggering new image
generation.

Acceptance criteria:

- Existing image requests route through wiki evidence tools.
- The answer may render only attachment images that appear in tool
  observations with `markdown_src`.
- The answer prompt forbids guessed local paths or invented image references.
- If the evidence contains only attachment metadata, description, topic, OCR, or
  source text, the answer bases image discussion on those fields and does not
  imply direct pixel-level visual inspection.
- Response style does not affect whether attachment evidence can be rendered.

### Generate A New Image

As a user explicitly asking KnoArbor to create a new visual asset, I can use the
configured image-generation provider.

Acceptance criteria:

- New visual creation intent routes to `generate_image`.
- Evidence-derived image generation is allowed only when the user explicitly
  asks to create a new visual asset.
- The generated-image prompt should include only the minimum wiki-derived
  details needed for the requested visual.
- Mermaid or textual diagram requests are answered as Markdown/Mermaid, not
  image generation.
- If a generated image must be based on current wiki evidence, the planner uses
  reusable evidence already available in the current turn or gathers evidence
  before a later generation step; it does not pretend that a same-plan search
  result is already available to the generated-image prompt.
- The final answer includes only image Markdown returned by the tool.

## Release Criteria

- Config schema, UI form schema, config rendering, and Settings UI support
  `chat.response_style`.
- Chat context assembly injects a bounded response-style instruction into the
  answer synthesis call.
- Tool planner prompt, answer prompt, and evidence-pack instructions have clear
  ownership boundaries and no impossible tool-action instructions in the
  answer stage.
- Prompt instructions clearly state that evidence text cannot override
  KnoArbor's system behavior, tool permissions, citation policy, or data
  handling rules.
- Attachment-image answers do not claim direct visual inspection unless visual
  analysis evidence exists.
- A small set of deterministic prompt fixture cases defines expected boundaries
  for concise, balanced, and deep behavior so future changes do not rely only
  on subjective manual judgment.
- Unit tests cover config persistence, style prompt injection, prompt boundary
  text, image route planning, and attachment path discipline.
- Existing chat retrieval, citation, streaming, and generated-image tests keep
  passing.
