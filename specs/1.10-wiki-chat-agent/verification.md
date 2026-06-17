# 1.10 Wiki Chat Agent Verification

## Automated Checks

Backend:

```bash
uv run python -m unittest tests.test_chat_agent
uv run python -m unittest discover tests
uv run ruff check src tests scripts
```

Frontend:

```bash
cd web
npm run build
```

Release gate:

```bash
scripts/release-check.sh
```

## Required Test Cases

- Search-only question returns a final answer with page citations.
- Search question returns a final answer grounded in the canonical evidence
  package.
- Invalid JSON model output raises a structured model-output error.
- Chat retrieval policy expands evidence for broad or comparative questions.
- Multi-vault query labels each cited page with vault information.
- `/chat/stream` emits progress events and a final `chat_response.v1` payload.
- `/chat/stream` emits `answer_delta` events during final answer synthesis when
  the selected provider adapter supports streaming.
- `/chat/stream` final response matches the persisted session record.

## Manual UI Checks

- Home page opens directly into Chat.
- Active vault change affects new chat requests.
- Evidence trace can be expanded without overwhelming the conversation.
- Page citations open the Knowledge Base.
- Model errors are readable and do not blank the page.
- Chat shows progress while retrieval or answer generation is still running.

## Non-Regression Checks

- `/query` remains model-free evidence retrieval.
- Ingest, lint, reports, runs, wiki pages, and skill routes keep working.
- UI navigation does not trigger expensive hidden diagnostics.
- No raw private vault data is committed by tests.

## Known Risks

- Small local models may fail JSON answer contracts.
- Long primary pages can make answers slow unless evidence projection is
  bounded.
- Streaming may require a separate compatibility decision later.
