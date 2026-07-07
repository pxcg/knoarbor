# 1.18 Chat Response Style And Prompt Governance Tasks

## P0 Prompt Governance Boundary Fixes

- [x] Confirm prompt governance boundary fixes remain in scope before shipping
  the Settings control.
- [x] Remove or rewrite answer-stage instructions that imply the answer
  synthesizer can call tools.
- [x] Add evidence-as-data prompt boundaries so wiki/source/attachment text
  cannot override system, tool, citation, or data-handling policy.
- [x] Add explicit attachment-image discipline: render only observed
  `markdown_src` values.
- [x] Add visual-evidence discipline: do not imply pixel-level image inspection
  without OCR, metadata, description, or future visual-analysis evidence.
- [x] Tighten `generate_image` planning text so evidence-based generation
  matches actual multi-round execution semantics and uses minimum necessary
  wiki-derived visual details.

## P1 Config And Settings

- [x] Add `chat.response_style` to core config with values `concise`,
  `balanced`, and `deep`.
- [x] Add UI form read/write fields for `chat_response_style`.
- [x] Preserve `chat.auto_ingest` while rendering the updated `chat` config.
- [x] Add Settings > General segmented control for answer depth.
- [x] Save style changes immediately and reload persisted form state after
  successful save.
- [x] Add English and Chinese UI labels.

## P2 Answer Style Injection

- [x] Add a small response-style instruction builder in the chat context or
  answer synthesis layer.
- [x] Inject the validated response-style system message into final answer
  synthesis.
- [x] Make explicit latest-turn length/detail instructions take precedence over
  the saved default response style.
- [x] Record selected `response_style` in chat response stats.
- [x] Update `wiki_chat_answer.md` with stable product voice and answer-depth
  rules.
- [x] Ensure the answer prompt keeps citations, evidence gaps, and attachment
  discipline independent from style.

## P3 Legacy And Deduplication Cleanup

- [ ] Deduplicate repeated evidence-role wording where it creates maintenance
  risk.
- [x] Decide whether `parse_answer_draft` is removable legacy code; remove it
  if no production path uses it.

## P4 Verification

- [x] Add config tests for default, valid, and invalid `chat.response_style`.
- [x] Add UI config form tests for style read/write and preservation of
  `chat.auto_ingest`.
- [x] Add chat context tests that verify style instructions are included in
  answer synthesis and not included in tool planning.
- [ ] Add prompt fixture tests for concise, balanced, deep, and explicit
  per-turn overrides such as "详细展开" and "只给结论".
- [ ] Add planner tests for existing attachment images vs new image generation.
- [ ] Add planner or loop tests for evidence-based image generation not relying
  on unavailable same-plan search output.
- [ ] Add answer prompt/evidence tests that forbid invented image paths.
- [x] Run backend chat tests.
- [x] Run frontend build.
- [x] Rebuild desktop app and service after implementation.

## Deferred

- [ ] Free-form per-vault custom instructions after enterprise policy review.
- [ ] Per-session temporary style override in the chat composer.
- [ ] Prompt evaluation dashboards for style adherence.
