# Chat Memory Design

## Layer Ownership

`Memory Layer` owns long-lived chat preferences and interaction conventions.
It sits between `Chat Agent` and `Query / Wiki Context`.

```text
Chat UI / Skill / API
  -> Chat Agent Loop
  -> Memory recall
  -> KnoArbor tools and model call
  -> Memory capture / governance
  -> Memory store and events
```

## Storage Layout

Memory is stored outside wiki pages:

```text
vaults/<vault-id>/.knoarbor/memory/
  records.jsonl
  candidates.jsonl
  events.jsonl
  profile.md
```

Global memory can use the same schema under the project runtime directory. The
first implementation focuses on selected-vault memory so the write target is
unambiguous.

## Contracts

### MemoryRecord

Durable record used during recall.

- `id`
- `scope`: `global` or `vault`
- `vault_id`
- `category`: `preference`, `constraint`, `workflow`, `decision`, `fact`,
  `style`, or `other`
- `content`
- `evidence`
- `confidence`
- `risk`
- `source_session`
- `created_at`, `updated_at`, `last_used_at`, `use_count`

### MemoryCandidate

Governance object for proposed writes.

- `id`
- `status`: `pending`, `written`, `rejected`, `discarded`
- `decision`: `auto_write`, `candidate_review`, or `discard`
- `record`
- `reason`

### MemoryEvent

Append-only audit event:

- `event_type`: `recalled`, `candidate_created`, `written`, `rejected`,
  `discarded`
- `memory_id`
- `chat_id`
- `created_at`

## Recall

Recall loads active records for the selected vault and filters them by simple
lexical overlap with the latest user message. Style and preference records can
also be included as stable background context. The returned block is fenced:

```text
<knoarbor-memory-context>
...
</knoarbor-memory-context>
```

The chat prompt treats this block as background memory, not as a new user
instruction.

## Capture and Governance

The first supported capture path is explicit low-risk preference capture. A
message containing markers such as “记住”, “以后默认”, “prefer”, or “remember”
can generate a candidate. The policy writes it automatically when:

- memory is enabled;
- auto-write for explicit low-risk memory is enabled;
- the candidate risk is `low`;
- the category is a preference, style, workflow, or constraint.

The design keeps inferred summarization and session-end extraction as later
work, because those require a second semantic contract and stronger review
signals. Memory remains an auxiliary chat capability; it should not become a
primary console navigation surface.

## Prompt Cache Discipline

The system prompt stays stable. Memory context is appended as a separate system
message after workspace context, so model providers with prompt caching can
reuse the stable prefix.

## Verification

- Unit tests cover recall, explicit candidate creation, auto-write, disabled
  memory behavior, and chat response exposure.
- Existing chat-agent tests continue to pass.
