# 1.10 Wiki Chat Agent Tasks

## P0 Contract And Backend Loop

- [x] Add chat request/response schemas.
- [x] Add chat answer service with bounded model calls.
- [x] Add `ChatContextEngine` for prompt/context assembly.
- [x] Add `ChatSessionStore` for vault-scoped persisted chat records.
- [x] Add chat answer schema validation.
- [x] Add bounded model-planned chat tools and page-first evidence planning.
- [x] Add `POST /chat`.
- [x] Add chat session list/read APIs.
- [x] Add manual chat-session ingest API.
- [x] Add close-session API with optional auto-ingest policy.
- [x] Convert stored chat sessions into `knoarbor_chat` `SourceDocument`
  values for the shared ingest document pipeline.
- [x] Consume query result roles: primary pages, supporting pages, and source
  pages.
- [x] Add unit tests for search -> evidence package -> final answer.
- [x] Add unit tests for invalid model output.
- [x] Remove user-facing retrieval depth controls from Chat.
- [x] Remove `execution_mode` from the public chat contract.
- [x] Add tests for internal chat tool planning and direct-answer guardrails.
- [x] Persist citations and tool traces per assistant turn.
- [x] Use persisted session history as the backend authority for chat turns.
- [x] Pass structured recent turn metadata to the tool planner without raw
  assistant prose.
- [x] Pass bounded recent conversation context to answer synthesis for natural
  follow-up questions while keeping wiki evidence as the grounding source.

## P1 Console Home Chat

- [x] Replace overview landing page with Chat.
- [x] Keep active vault selector visible and reflected in chat requests.
- [x] Add message thread, composer, examples, citations, and source cards.
- [x] Add run/report/page cards for tool results.
- [x] Keep old operational status in Runs/Sources/Reports/Settings rather than
  duplicating it on Chat.
- [x] Restore recent chat sessions from the backend instead of front-end state
  only.
- [x] Add console actions for manual chat-session ingest and close-session
  policy evaluation.

## P2 Observability And Reports

- [x] Record model call metrics in token ledger with `flow=chat`.
- [x] Emit lightweight chat events for tool calls and failures.
- [x] Add readable error states for model unavailable, no results, retrieval
  failure, and invalid answer output.
- [ ] Add optional chat transcript export only after privacy review.

## P3 Docs And Release Surface

- [x] Update API docs with `/chat`.
- [x] Update architecture docs with Wiki Chat Agent layer.
- [ ] Update console screenshots after UI changes.
- [x] Update skill docs to clarify `/query` vs `/chat` usage.

## Deferred

- [ ] Streaming responses.
- [ ] Native provider tool calling.
- [ ] Scheduling or proactive daily summaries.
- [ ] Cross-vault merge recommendations from chat.
