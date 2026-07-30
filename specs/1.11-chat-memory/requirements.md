# Chat Memory Requirements

## Goal

Give the KnoArbor chat surface a durable preference layer so answers can adapt
to user style, workflow preferences, and vault-specific conventions without
turning memory into another wiki or raw-source archive.

## User Scenarios

- A user states an explicit preference such as “以后默认用中文回答”. Later chat
  turns should receive that preference as background context.
- A user works in different vaults with different conventions. Vault-specific
  memory should follow the selected vault.
- A user should be able to inspect which memories were used or written by a chat
  response through the chat response payload or technical reports.
- Memory writes should be auditable and low-risk. Inferred memories that need
  judgement should be represented as candidates rather than hidden writes.

## Requirements

- Chat memory is a separate architecture layer from wiki pages, raw sources,
  query context, and reports.
- Memory records support scope, category, evidence, confidence, risk, source
  session, and usage metadata.
- Chat recall must be injected as fenced background context, not merged into the
  user message text.
- Explicit low-risk preferences can be written automatically.
- Inferred or high-risk memories must be stored as candidates or discarded by
  policy.
- Memory events must be append-only and inspectable.
- Memory storage must stay outside `pages/` so Obsidian wiki views remain clean.

## Non-Goals

- Replacing wiki pages or source records.
- Storing arbitrary full chat transcripts as memory.
- Adding a database requirement.
- Adding an external memory provider.
- Building a generalized autonomous assistant memory framework.
- Adding a dedicated front-end memory management surface.

## Acceptance Criteria

- A chat request can recall existing memory records for the selected vault.
- A chat response can write an explicit user preference to the memory store.
- The response exposes `memory_used`, `memory_candidates`, and `memory_writes`.
- Memory storage is append-only JSONL under `.knoarbor/memory/`.
- The behavior is covered by unit tests.
