# Chat Memory Verification

## Automated

```bash
uv run python -m unittest tests.test_chat_agent tests.test_memory_service
uv run ruff check src tests scripts integrations/skills/knoarbor-local/scripts/knoarbor.py
```

## Manual

- Start the service and send a chat message that explicitly asks KnoArbor to
  remember a low-risk preference.
- Confirm the chat response includes a memory write.
- Send a follow-up chat request in the same vault.
- Confirm the model receives a fenced memory context and the response exposes
  memory usage.

## Risks

- Explicit preference extraction is deterministic and conservative. It does not
  infer hidden preferences from ordinary messages.
- Memory records are append-only in the first implementation. Editing and
  rejection workflows belong to the next UI/CLI management phase.
