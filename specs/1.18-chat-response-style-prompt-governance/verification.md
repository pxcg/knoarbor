# 1.18 Chat Response Style And Prompt Governance Verification

## Automated Checks

Backend:

```bash
.venv/bin/python -m unittest tests.test_core_config
.venv/bin/python -m unittest tests.test_chat_agent
.venv/bin/python -m unittest tests.test_chat_tool_flows
.venv/bin/python -m unittest tests.test_chat_evidence
.venv/bin/python -m unittest tests.test_chat_retrieval_policy
```

Frontend:

```bash
cd web
npm run build
```

Desktop release check after implementation:

```bash
cd desktop
npm run build
npm run build:service
```

## Required Test Cases

- Missing `chat.response_style` resolves to `balanced`.
- Valid response styles round-trip through config loading, UI form rendering,
  and config saving.
- Invalid response styles fail validation.
- Settings > General commits response style immediately.
- Answer synthesis receives the selected style instruction.
- Tool planning does not receive style-specific answer prose.
- Explicit latest-turn style requests override the default style:
  - `concise` plus "详细展开" can produce a detailed answer;
  - `deep` plus "只给结论" can produce a short answer.
- Prompt fixtures cover concise, balanced, and deep instruction generation
  without relying on subjective manual length judgment.
- Wiki/source/attachment evidence containing instruction-like text such as
  "ignore previous instructions" is treated as data and cannot change tool,
  citation, or data-handling policy.
- Concise style does not skip wiki retrieval for knowledge questions.
- Deep style does not expand citations beyond evidence used in the answer.
- Existing image requests route through wiki evidence tools and render only
  observed attachment Markdown.
- Existing image answers do not claim pixel-level visual inspection unless the
  evidence includes OCR, metadata, descriptions, or explicit visual-analysis
  results.
- New image creation requests route through `generate_image`.
- Evidence-derived generated-image prompts contain only the minimum necessary
  wiki-derived details for the requested visual.
- Mermaid diagram requests do not trigger `generate_image`.
- Evidence-based generated-image requests do not assume a same-plan
  `query_wiki` result is available unless execution semantics support it.
- Answer synthesis cannot invent local attachment paths.

## Manual UI Checks

- Settings > General shows the answer-depth control below language.
- Selecting each style updates the saved config and remains selected after
  reopening Settings.
- A concise style chat answer is visibly shorter for a simple question.
- A deep style answer expands architecture or design questions without losing
  citations.
- Chinese prompts receive natural professional Chinese.
- Existing attachment image requests show existing images when evidence
  contains them.
- Existing attachment image answers are worded from available descriptions or
  metadata rather than claiming direct visual understanding.
- Explicit generated-image requests display generated images and do not
  confuse them with existing attachments.

## Non-Regression Checks

- Chat streaming still emits progress, answer deltas, and final response.
- Existing citations and source cards still resolve.
- Model provider configuration remains unchanged by style selection.
- Image generation provider settings remain unchanged by style selection.
- Ingest, query, wiki browsing, and chat-session persistence keep working.

## Known Risks

- Small local models may over-obey length instructions and omit useful caveats;
  tests should assert evidence rules are still present.
- Too much style prompt text can dilute evidence instructions; keep generated
  style messages short.
- A global style setting can be misunderstood as a hard per-turn command; the
  generated instruction and UI label must frame it as the default answer depth.
- Prompt governance fixes may look like copy edits, but incorrect ownership
  language can cause runtime behavior errors; include boundary tests instead of
  relying only on prompt review.
- Evidence-derived image generation can expose knowledge-base summaries to an
  image provider; keep generation explicit and the prompt minimal.
- Users may assume rendered attachments mean the model has visual perception;
  wording and tests should keep metadata/OCR/visual-analysis boundaries clear.
- A future free-form custom instruction feature could conflict with enterprise
  policy if added without a separate review.
