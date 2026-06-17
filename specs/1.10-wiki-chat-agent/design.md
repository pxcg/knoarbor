# 1.10 Wiki Chat Agent Design

## Positioning

Wiki Chat is a KnoArbor console capability for asking natural-language
questions about maintained vaults. It is a page-first wiki question-answering
surface: KnoArbor chooses the evidence package deterministically, then the model
synthesizes an answer from that package.

It is not a general tool-running agent. Workflow operations such as ingest,
lint, cancellation, and report navigation remain explicit UI/API actions.

```text
Console Chat
  -> Chat API
  -> ChatContextEngine
  -> ChatRetrievalContextBuilder
  -> ChatEvidencePlanner
  -> Model Gateway
  -> Answer Synthesizer
  -> Query / Wiki
  -> ChatSessionStore
  -> Chat response with answer, citations, optional trace, and session record
```

## References Considered

Local reference systems:

- `itp-inspectx` Agent Loop: useful for evented loop state, tool cycle,
  checkpoint boundaries, and UI trace ideas.
- Hermes Agent: useful for context building, prompt layering, memory
  compression, and long-running tool discipline.
- KnoArbor skill: useful for evidence-first host-AI usage and public API
  parity.

Adopted ideas:

- bounded model-planned KnoArbor tools with deterministic answer-set selection;
- explicit event/evidence trace;
- model answer synthesis separated from evidence selection;
- stable context package before model calls;
- no side-effect workflow execution from chat.

Rejected ideas:

- generic tool registry with shell/browser/file tools;
- native provider-specific tool calling as the only protocol;
- chat page owning workflow behavior;
- treating chat as the only query interface.

## Owning Layers

| Layer | Responsibility |
| --- | --- |
| UI | Chat layout, message state, citations, and links to pages/reports/runs. |
| API | Stable `/chat`, `/chat/stream`, `/chat/sessions`, and `/chat/sessions/{session_id}` contracts. |
| Service | Chat orchestration, deterministic retrieval, model calls, response assembly. |
| Context | Stable system prompt, workspace context, memory context, and recent session messages. |
| Storage | Vault-scoped chat session records under `.knoarbor/chat/`. |
| Semantic | Chat answer prompt and JSON answer schema. |
| Model Gateway | Provider-neutral chat completion, retry, metrics, capability errors. |
| Retrieval | Selects the canonical first-pass wiki evidence package from the user question and vault scope. |
| Evidence Planning | Converts rich query results into bounded model-facing evidence packs. |
| Session Topic Anchor | Maintains a soft, updateable conversation focus for follow-up planning and synthesis. |
| Runtime / Audit | Optional run/event records, failure reports, token ledger entries. |

## Public API

Endpoint:

```text
POST /chat
```

Request:

```json
{
  "schema_version": "chat_request.v1",
  "session_id": "chat_abc123",
  "config_path": "config.yaml",
  "vault_id": "default",
  "vault_ids": [],
  "all_vaults": false,
  "messages": [
    {"role": "user", "content": "Agent Loop 是什么？"}
  ],
  "max_turns": 6,
  "include_trace": true
}
```

Response:

```json
{
  "schema_version": "chat_response.v1",
  "session_id": "chat_abc123",
  "answer": "...",
  "messages": [],
  "citations": [
    {"kind": "page", "path": "concepts/Agent-Loop-and-Control-Patterns.md", "title": "Agent Loop and Control Patterns", "vault_id": "default"}
  ],
  "tool_trace": [
    {"tool": "query_wiki", "arguments": {}, "status": "ok", "summary": "..."}
  ],
  "run_links": [],
  "stats": {
    "retrieval_strategy": "model_planned_tools",
    "tool_plan": {"tool_calls": [{"name": "query_wiki", "arguments": {"query": "Agent Loop 是什么？"}}]},
    "model_calls": 2,
    "tool_calls": 1,
    "total_tokens": 1234
  },
  "warnings": []
}
```

Session APIs:

```text
GET /chat/sessions
GET /chat/sessions/{session_id}
```

Streaming endpoint:

```text
POST /chat/stream
```

`/chat/stream` accepts the same `ChatRequest` as `/chat` and returns
`text/event-stream`. The final event contains the same `ChatResponse` shape as
`POST /chat`.

Event contract:

```text
event: stage
data: {"stage":"tool_plan","message":"Calling chat tool planner."}

event: tool
data: {"event_type":"tool_call_finished","tool":"query_wiki","status":"ok","message":"Found 6 wiki result(s)."}

event: answer_delta
data: {"delta":"Agent Loop "}

event: final
data: {"schema_version":"chat_response.v1","answer":"...","citations":[]}

event: error
data: {"message":"...","code":"..."}
```

Design rules:

- streaming reuses the normal chat service and does not fork retrieval,
  citation, memory, or session persistence behavior;
- progress events are derived from the same internal `ChatEvent` stream stored
  on the final response;
- final answer token streaming is owned by `ModelGateway` provider adapters and
  appears as `answer_delta` events on the same `/chat/stream` connection;
- token deltas are provisional display text. The final `chat_response.v1`
  remains the canonical answer after citations, session persistence, and token
  ledger recording complete;
- clients can fall back to `/chat` without changing request payloads.

## Chat Session Store

Session records are vault-scoped runtime records:

```text
vaults/<vault-id>/.knoarbor/chat/
  sessions/
    chat_<id>.json
```

The store owns:

- stable session ID generation;
- title and timestamp updates;
- appended messages;
- citations, evidence traces, events, run links, memory metadata, warnings, and
  usage stats;
- list/read APIs for the console.

It does not own final answer generation, prompt decisions, wiki page content,
or maintained page writes.

## Chat Context Engine

The context engine builds model messages for each chat turn:

```text
stable system prompt
  -> workspace/vault context
  -> optional memory context
  -> recent persisted and request messages
```

This keeps prompt assembly out of the loop executor and makes later prompt
cache, token-budget, and memory improvements local to one layer.

The persisted session is the authority for conversation history. UI requests
may send the current user message and a small display window, but the backend
merges it with the stored session before planning and answering.

Conversation history is passed to the model in two different forms:

- tool planning receives structured turn metadata: recent user messages,
  citation paths, answer page paths, source page paths, and tool summaries;
- answer synthesis receives a bounded recent conversation context with user
  messages, assistant answer excerpts, and citation paths.

Planner input does not include raw assistant prose. This keeps JSON tool
planning stable and prevents prior answer wording from becoming a new tool
instruction. Answer synthesis can see bounded assistant excerpts so follow-up
questions such as "展开第二点" or "它和上面方案的关系是什么" remain natural.
The evidence package remains the only grounding source for factual claims.

## Session Topic Anchor

Multi-turn wiki chat keeps a structured topic anchor on the session record:

```json
{
  "active_topic": "Agent Loop / OpenClaw",
  "active_goal": "Design a production agent architecture",
  "key_entities": ["Agent Loop", "OpenClaw", "MCP", "A2A"],
  "recent_answer_type": "architecture",
  "relation_to_previous": "continue",
  "excluded_directions": []
}
```

The anchor is a service-owned dialogue state, not a model-generated memory and
not a retrieval filter. It is built deterministically from the latest user
message, persisted session metadata, and evidence returned by tools.

Relation values:

- `continue`: the latest turn stays on the same topic;
- `refine`: the user asks to expand, detail, or exemplify a known point;
- `synthesize`: the user asks to summarize, organize, or turn prior discussion
  into a plan or document;
- `side_question`: the user briefly asks about a related object without
  replacing the main topic;
- `switch`: the user introduces a new topic and old evidence should not be
  forced into the answer.

Design rules:

- the anchor guides query rewriting, context reuse, and answer identity;
- it never prevents a clear topic switch;
- factual claims still require current tool evidence;
- synthesis turns may reuse prior evidence when sufficient;
- side questions can use related evidence without overwriting the active goal.

## Tool Planning And Retrieval Policy

Chat does not expose `quick`, `balanced`, or `deep` as user-facing modes. The
service asks a bounded tool planner to decide whether the current turn needs
wiki search, page reads, prior evidence reuse, or a direct non-wiki answer.

Available chat tools are intentionally narrow:

- `query_wiki`: search maintained wiki pages for a topic.
- `read_wiki_page`: read one known maintained page by path.
- `reuse_context`: reuse prior evidence in the same chat when a follow-up stays
  within the previously retrieved pages.
- `answer_directly`: answer greetings, UI/help questions, or other turns that
  do not need wiki evidence.

The planner may choose the wiki query text and tool sequence, but the service
keeps code-owned guardrails:

- knowledge questions must use wiki evidence, even when the planner requests a
  direct answer;
- direct answers are limited to greetings, help, and UI-style questions;
- every returned citation must be supported by a tool trace;
- query results still pass through the deterministic page-level answer-set
  selector before answer synthesis.

The lower-level `/query` API may continue exposing retrieval controls for tools,
debugging, and host-AI integrations. Chat is the product-facing question-answer
surface and keeps those controls internal.

## Page-First Query Semantics

KnoArbor wiki pages are already curated knowledge units. Chat retrieval should
therefore treat pages as answer-bearing objects, not as interchangeable RAG
chunks.

`query_wiki` returns:

- `answer_scope`: whether the query is narrow, broad, or exploratory;
- `answer_set`: the recommended answer-bearing page set by path;
- `primary_pages`: maintained pages that directly answer the current question;
- `supporting_pages`: related maintained pages that add mechanisms,
  implementation details, caveats, comparisons, or follow-up context;
- `source_pages`: source digest pages for provenance.

The chat service synthesizes an answer from the primary page when it answers the
question, enriches it with supporting pages when useful, and cites the pages it
used. The raw query response is retained for UI trace and API inspection, while
`ChatEvidencePlanner` produces the model-facing `evidence_pack` for answer
synthesis.

The evidence pack owns:

- answer action guidance such as `answer_from_evidence`,
  `read_primary_if_detail_needed`, or `answer_with_gap`;
- primary page content as the opening anchor;
- primary/supporting page bodies as the answer-bearing wiki material;
- source page summaries for provenance;
- weak-evidence and missing-facet signals.

This keeps token budgeting and evidence sufficiency out of the prompt while
preserving page-first wiki semantics. Chat should present a page list only when
the user explicitly asks to list pages, browse the vault, or choose from
candidates.

## Answer Control

Default chain:

```text
system prompt
  -> user/history messages
  -> bounded chat tool planning
  -> guarded KnoArbor tool execution
  -> canonical evidence package
  -> model answer synthesis
  -> validated answer draft
```

Streaming chain:

```text
POST /chat/stream
  -> same ChatAgentService loop
  -> emit lifecycle/tool/model events as SSE
  -> persist final session record
  -> emit final ChatResponse
```

Rules:

- Chat performs one planning step before answer synthesis.
- Streaming and synchronous chat share the same planning and answer synthesis
  path.
- The planner can use `query_wiki`, `read_wiki_page`, `reuse_context`, or
  `answer_directly`; it cannot access shell, browser, arbitrary files, or
  external workflow tools.
- The model receives the evidence package and produces only an answer draft
  with citations.
- The answer model also receives bounded conversation context for continuity,
  but it treats that context as dialogue state rather than factual evidence.
- Evidence packages include stable IDs, paths, vault labels, and openable links.
- Invalid model JSON is reported as a model output error with enough context for
  the caller to retry through the normal request boundary.
- Chat answer synthesis does not write wiki pages. A persisted chat session can
  be handed to `/ingest` as a `knoarbor_chat` source document through explicit
  session ingest or the close-session auto-ingest policy.

Retrieval policy:

- A known maintained page can be used as an anchor for a broad question.
- Broad architecture, comparison, design, production, or multi-facet questions
  must not finish from one anchor page alone.
- When the current evidence only contains an anchor page, the loop asks for a
  supporting `query_wiki` evidence set before answer synthesis.
- Explicit page-reading and narrow follow-up detail requests may finish from a
  single maintained page.

## Session Turn Records

Chat sessions are stored as ordered turn records. Each assistant turn owns its
own citations, tool trace, events, run links, memory metadata, stats, and
warnings. Session-level fields may expose the latest turn for summaries, but UI
restore and context reuse read from turn records so one answer's citations do
not leak into other answers.

## Context Strategy

Prompt layering:

- stable system prompt: role, answer schema, evidence-use rules;
- semi-stable workspace context: active vault and available vaults;
- dynamic conversation: user messages and canonical evidence package.

This preserves model prompt-cache potential without hiding user-specific
context inside the stable prompt.

Evidence packages should be structured data, not unbounded raw retrieval
responses. Because KnoArbor pages are already curated and compressed during
ingest, answer-bearing `primary_pages` and `supporting_pages` should preserve
their maintained body content whenever they are selected for the answer set.
Source pages and further-reading candidates remain summary-level unless the
user asks for provenance or a specific page.

## UI Design

The home page becomes `Chat`.

Primary regions:

- message thread;
- composer with examples;
- collapsible context panel for citations and evidence trace;
- active vault selector inherited from the global console shell.

Interaction rules:

- query/read answers show citations inline and as cards;
- evidence trace is collapsed by default and readable when opened;
- page citations can open the Knowledge Base without losing chat state.

The old overview status cards move to Runs, Sources, Reports, or Settings. Chat
is the primary landing page.

## Chat Session Ingest

Chat sessions are durable runtime records, not maintained wiki pages. When a
session contains reusable knowledge, it can enter the normal wiki compilation
pipeline as an internal source.

```text
ChatSessionStore
  -> ChatSessionRecord
  -> knoarbor_chat SourceDocument
  -> /ingest document workflow
  -> segmentation / semantic ingest / write / report / checkpoint
```

Manual trigger:

```http
POST /chat/sessions/{session_id}/ingest
```

Close-session trigger:

```http
POST /chat/sessions/{session_id}/close
```

The close endpoint marks the session closed and evaluates
`chat.auto_ingest`. It always records a deterministic ingest-candidate summary
on the session record. If the policy matches, it queues the same document
ingest workflow and stores the resulting `run_id` on the session record.

Design rules:

- the chat page never writes wiki markdown directly;
- chat-session ingest uses `knoarbor_chat` as the source type;
- chat sessions use turn-based segmentation and session checkpoints;
- candidate detection records durable knowledge signals only; it does not write
  pages and does not call an additional model;
- auto ingest is off by default and starts only on an explicit close event;
- manual ingest remains available regardless of the auto policy.

## Chat Answer Regeneration

Regeneration is a turn-level retry for the latest completed assistant answer.
It is not a new user message and it does not create a forked session in the
first product version.

```text
POST /chat/sessions/{session_id}/retry
  -> ChatSessionStore.prepare_retry_latest_turn
  -> trim latest user+assistant turn
  -> run normal /chat loop with the same user message
  -> persist replacement answer
  -> restore previous session if regeneration fails
```

Design rules:

- retry is available only for active sessions with at least one completed turn;
- the backend owns turn trimming so the UI cannot duplicate user messages;
- the normal chat agent loop, retrieval, citations, memory, and ledger paths are
  reused;
- failed retry restores the previous answer.

## Failure Handling

Failures use existing error envelopes and codes.

Expected failure surfaces:

- model unavailable;
- invalid answer JSON;
- wiki retrieval failed;
- page/report/run not found;

The chat response should tell the user what happened and offer the next safe
action. Backend logs and token ledger should contain retrieval/model timing.

## Relationship To Existing Query And Skill

`/query` remains evidence retrieval and does not call an answer model.

The bundled host-AI skill remains retrieval-first because host AI owns the
conversation. It may call `/chat` only when the user explicitly wants KnoArbor
to synthesize an answer inside KnoArbor rather than return evidence to the host
AI.

## Rejected Alternatives

### Put Chat Logic Into The Query Page

Rejected because query is a retrieval API with stable no-model semantics.

### Use A Generic Agent Runtime

Rejected because KnoArbor needs a bounded knowledge-console agent, not a
general automation platform.

### Let The Prompt Read Files Or Decide Storage

Rejected because prompts remain semantic contracts. File reads, reports,
workflow starts, and storage policy belong to services and pipelines.

### Make Side Effects Fully Implicit

Rejected because ingest, lint, and cancellation alter runtime state. They
require clear intent and visible run IDs.
