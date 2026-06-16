# 1.10 Wiki Chat Agent Requirements

## Problem

KnoArbor already supports ingest, lint, query, wiki browsing, reports, runs,
and host-AI skills. The console still requires users to choose the right page
and endpoint before asking natural questions about the vault.

The home surface should become a conversation-first KnoArbor interface: users
can ask about their maintained wiki and inspect cited pages from one place.
This is a KnoArbor product capability, not a general-purpose agent platform.

## Goals

- Replace the console home page with a Wiki Chat interface.
- Add a bounded wiki answer service that retrieves canonical page evidence
  before model answer synthesis.
- Persist chat sessions so follow-up questions can resume prior user turns,
  answers, citations, traces, and usage.
- Separate chat context assembly from loop execution so prompt layering,
  memory recall, vault context, and recent messages have a clear owner.
- Keep final answer generation inside KnoArbor Chat only for console usage; the
  host-AI skill remains evidence-first and can still let the host AI answer.
- Support active-vault and multi-vault context explicitly.
- Make evidence selection inspectable through UI trace, API response, and token
  metrics.
- Keep the same model gateway and provider abstraction used by ingest and lint.
- Reuse existing query and wiki page services for evidence selection and page
  navigation.
- Allow a persisted KnoArbor chat session to become a normal ingest source
  through explicit user action or the configured close-session policy.
- Preserve SDD layer boundaries: services select evidence; prompts synthesize
  answers; storage, reports, and lifecycle remain outside prompts.

## Non-Goals

- Do not expose arbitrary shell, browser, filesystem, network, or workflow tools
  through chat.
- Do not build a generic assistant framework that competes with Hermes,
  Claude Code, Codex, OpenClaw, or opencode.
- Do not duplicate ingest, lint, query, or wiki-read logic in the chat service.
- Do not let the chat page write wiki pages directly; chat-session ingest must
  go through the shared ingest document pipeline.
- Do not make chat required for existing CLI, API, skill, or workflow usage.
- Do not require host-AI skills to expose retrieval tuning. Skills can reuse
  chat for answer synthesis or use `/query` for raw evidence retrieval.
- Do not implement long-term user accounts, multi-user sessions, or TLS in this
  feature.

## User Scenarios

### Continue A Chat Session

As a console user, I can ask several follow-up questions in the same chat and
refresh the page without losing the previous exchange.

Acceptance criteria:

- The response includes a stable `session_id`.
- The service stores messages, citations, evidence traces, events, memory metadata,
  and usage for the session.
- A later request with the same `session_id` can continue from the persisted
  session without relying only on front-end state.
- Session records are stored under `.knoarbor/chat/`, outside maintained wiki
  pages and raw sources.

### Ask About The Active Vault

As a console user, I can ask "Agent Loop 是什么？" and get an answer grounded in
the selected KnoArbor vault.

Acceptance criteria:

- The service searches the active vault before answering.
- The response shows which pages or reports were used.
- The user can open referenced pages from the answer.

### Read A Specific Page

As a user, I can ask "打开 Agent Loop and Control Patterns 的全文" and see the
page content or a readable summary when the page is long.

Acceptance criteria:

- The service can search for candidate pages and cite the selected maintained
  page.
- The UI shows the page reference and provides a direct Knowledge Base link.
- Long page handling is explicit: the agent can summarize, ask whether to read
  more, or read sections.

### Multi-Vault Awareness

As a user with multiple configured vaults, I can ask across one vault or all
vaults without losing which vault a page came from.

Acceptance criteria:

- The request includes selected vault context.
- Multi-vault results label vault ID/name/path.
- The answer and citations preserve which vault each cited page came from.

### Preserve A Useful Chat As Wiki Knowledge

As a console user, I can manually compile the current chat session into the
selected wiki when the conversation contains reusable knowledge.

Acceptance criteria:

- The manual action converts the stored session into a `knoarbor_chat`
  `SourceDocument`.
- The action queues the same ingest document workflow used by other source
  documents.
- The session record stores the queued ingest `run_id`.

### Close-Session Auto Ingest

As a user who opts into automation, I can close a chat session and let
KnoArbor queue ingest when the configured policy matches.

Acceptance criteria:

- Auto ingest is disabled by default.
- The policy uses `chat.auto_ingest.enabled`, `trigger`, and `min_user_turns`.
- Closing a session records an ingest-candidate summary even when auto ingest
  remains disabled.
- The auto path shares the same source document and ingest workflow as manual
  chat-session ingest.

## Release Criteria

- `POST /chat` has a stable request and response schema.
- Chat session list/read APIs expose persisted session summaries and records.
- Chat session ingest and close APIs expose queued run metadata when a session
  is sent to ingest.
- The console home page is a chat interface backed by `/chat`.
- Evidence traces are visible but not overwhelming.
- Chat uses existing model gateway, retry, error codes, and token metrics.
- Unit tests cover chat tool planning, direct-answer guardrails, invalid model
  output, answer synthesis, citations, and turn-level session persistence.
- UI tests or screenshots cover the home chat view and a successful evidence trace.
