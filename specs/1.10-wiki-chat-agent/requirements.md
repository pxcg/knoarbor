# 1.10 Wiki Chat Agent Requirements

## Problem

KnoArbor already supports ingest, lint, query, wiki browsing, reports, runs,
and host-AI skills. The console still requires users to choose the right page
and endpoint before asking natural questions about the vault.

The home surface should become a conversation-first KnoArbor interface: users
can ask about their maintained wiki, inspect pages, understand reports, and
start supported workflows from one place. This is a KnoArbor product capability,
not a general-purpose agent platform.

## Goals

- Replace the console home page with a Wiki Chat interface.
- Add a bounded Agent Loop that can reason over KnoArbor-specific tools.
- Persist chat sessions so follow-up questions can resume prior user turns,
  answers, citations, traces, and usage.
- Separate chat context assembly from loop execution so prompt layering,
  memory recall, vault context, and recent messages have a clear owner.
- Keep final answer generation inside KnoArbor Chat only for console usage; the
  host-AI skill remains evidence-first and can still let the host AI answer.
- Support active-vault and multi-vault context explicitly.
- Make tool usage inspectable through UI trace, API response, and optional run
  events.
- Keep the same model gateway and provider abstraction used by ingest and lint.
- Reuse existing query, wiki page, report, run, source, and workflow services.
- Preserve SDD layer boundaries: prompts decide next actions; services execute
  tools; storage, reports, and lifecycle remain outside prompts.

## Non-Goals

- Do not expose arbitrary shell, browser, filesystem, or network tools.
- Do not build a generic assistant framework that competes with Hermes,
  Claude Code, Codex, OpenClaw, or opencode.
- Do not duplicate ingest, lint, query, or wiki-read logic in the chat service.
- Do not make chat required for existing CLI, API, skill, or workflow usage.
- Do not replace the host-AI skill's retrieval-first behavior.
- Do not implement long-term user accounts, multi-user sessions, or TLS in this
  feature.

## User Scenarios

### Continue A Chat Session

As a console user, I can ask several follow-up questions in the same chat and
refresh the page without losing the previous exchange.

Acceptance criteria:

- The response includes a stable `session_id`.
- The service stores messages, citations, tool traces, events, memory metadata,
  and usage for the session.
- A later request with the same `session_id` can continue from the persisted
  session without relying only on front-end state.
- Session records are stored under `.knoarbor/chat/`, outside maintained wiki
  pages and raw sources.

### Ask About The Active Vault

As a console user, I can ask "Agent Loop 是什么？" and get an answer grounded in
the selected KnoArbor vault.

Acceptance criteria:

- The agent searches the active vault before answering unless the conversation
  already contains sufficient cited context.
- The response shows which pages or reports were used.
- The user can open referenced pages from the answer.

### Read A Specific Page

As a user, I can ask "打开 Agent Loop and Control Patterns 的全文" and see the
page content or a readable summary when the page is long.

Acceptance criteria:

- The agent can search for candidate pages, then read a selected page.
- The UI shows the page reference and provides a direct Knowledge Base link.
- Long page handling is explicit: the agent can summarize, ask whether to read
  more, or read sections.

### Explain A Run Or Report

As a user, I can ask "刚才的 lint 为什么没有修复？" and get an explanation based
on run records and reports.

Acceptance criteria:

- The agent can list recent runs and read a report.
- It explains status, applied operations, rejected operations, and next actions
  using report content.
- It does not invent report details that are not present.

### Start A Supported Workflow

As a user, I can ask "编译 Codex 最新记录" or "运行一次结构校验".

Acceptance criteria:

- Side-effect workflows are explicit tool categories.
- Safe workflows can be started when the intent is clear.
- The answer returns run ID, status, and report/runs links.
- Dangerous or ambiguous requests are converted into a clarification question,
  not hidden execution.

### Multi-Vault Awareness

As a user with multiple configured vaults, I can ask across one vault or all
vaults without losing which vault a page came from.

Acceptance criteria:

- The request includes selected vault context.
- Multi-vault results label vault ID/name/path.
- The agent can ask the user to choose a vault when a side-effect operation is
  ambiguous.

## Release Criteria

- `POST /chat` has a stable request and response schema.
- Chat session list/read APIs expose persisted session summaries and records.
- The console home page is a chat interface backed by `/chat`.
- Tool traces are visible but not overwhelming.
- Chat uses existing model gateway, retry, error codes, and token metrics.
- Unit tests cover loop control, tool dispatch, invalid model output, and
  multi-step search/read/final flows.
- UI tests or screenshots cover the home chat view and a successful tool trace.
