# 1.10 Wiki Chat Agent Tasks

## P0 Contract And Backend Loop

- [x] Add chat request/response schemas.
- [x] Add `WikiChatAgentService` with bounded loop control.
- [x] Add `ChatContextEngine` for prompt/context assembly.
- [x] Add `ChatSessionStore` for vault-scoped persisted chat records.
- [x] Add chat decision schema validation.
- [x] Add read-only tool registry: search wiki, read page, list pages, read
  report, list runs, list sources.
- [x] Add workflow tool registry: start ingest, start lint, cancel run.
- [x] Add `POST /chat`.
- [x] Add chat session list/read APIs.
- [x] Consume query result roles: primary pages, supporting pages, and source
  pages.
- [x] Add unit tests for tool-call -> observation -> final answer.
- [x] Add unit tests for invalid model output, unknown tool, and repeated tool
  calls.
- [x] Add unit tests for max turns and side-effect ambiguity.

## P1 Console Home Chat

- [x] Replace overview landing page with Chat.
- [x] Keep active vault selector visible and reflected in chat requests.
- [x] Add message thread, composer, examples, citations, and source cards.
- [x] Add run/report/page cards for tool results.
- [x] Keep old operational status in Runs/Sources/Reports/Settings rather than
  duplicating it on Chat.
- [x] Restore recent chat sessions from the backend instead of front-end state
  only.

## P2 Observability And Reports

- [x] Record model call metrics in token ledger with `flow=chat`.
- [x] Emit lightweight chat events for tool calls and failures.
- [x] Add readable error states for model unavailable, no results, ambiguous
  workflow, and max turns.
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
