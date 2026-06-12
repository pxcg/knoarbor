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
- Search then read page returns a final answer grounded in the read page.
- Recent run/report question reads a report and explains it.
- Ambiguous ingest request asks for clarification instead of starting a run.
- Explicit lint request queues a run and returns run ID.
- Unknown tool decision is rejected.
- Invalid JSON model output raises a structured model-output error.
- Max-turn exhaustion returns a partial grounded response and warning.
- Multi-vault query labels each cited page with vault information.

## Manual UI Checks

- Home page opens directly into Chat.
- Active vault change affects new chat requests.
- Tool trace can be expanded without overwhelming the conversation.
- Page citations open the Knowledge Base.
- Run cards open Runs or Reports.
- Model errors are readable and do not blank the page.

## Non-Regression Checks

- `/query` remains model-free evidence retrieval.
- Ingest, lint, reports, runs, wiki pages, and skill routes keep working.
- UI navigation does not trigger expensive hidden diagnostics.
- No raw private vault data is committed by tests.

## Known Risks

- Small local models may fail JSON decision contracts.
- Long page reads can make answers slow unless tool result projection is
  bounded.
- Side-effect tools need conservative intent checks to avoid surprising users.
- Streaming may require a separate compatibility decision later.
