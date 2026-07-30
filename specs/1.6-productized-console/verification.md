# 1.6 Productized Console Verification

## Automated Checks

Required when console behavior changes:

```bash
cd renderer && npm run build
cd renderer && npm run test:e2e
uv run python -m unittest tests.test_ui_api tests.test_api_surface
uv run python scripts/check-doc-links.py
```

Focused navigation acceptance must prove:

- every vault-scoped page renders the shared page-local vault switcher;
- Chat all-vault scope does not change the concrete workspace vault;
- primary Chat navigation retains the conversation while explicit New Chat
  resets it through the same command from UI and desktop menu;
- switching away and back retains Chat, query, Wiki, graph, report, and token
  interaction state;
- Wiki, graph, and report targets select the requested vault and are consumed
  once;
- target resolution waits for authoritative data and terminates with local
  feedback when the target no longer exists;
- terminal ingest invalidates page, graph, and query caches even when polling
  never observed a non-zero active-run count;
- Wiki targets use the backend resolver, reserve deleted feedback for a real
  404, and present materialization pending as a rebuildable view state;
- reports with the same path in different vaults resolve by composite identity.
- hidden retained pages issue no vault-change polling or automatic detail
  requests;
- changing Chat scope starts a new scoped session;
- run links resolve the exact persisted record by vault, run ID, and flow.
- Raw Markdown renders inline and block TeX as KaTeX without requiring network
  assets or enabling arbitrary HTML.

## Manual UI Review

Inspect at least:

- Chat and its explicit new-session actions.
- Flows: run monitor, ingest, lint, query, reports, and tokens.
- Knowledge: Wiki pages and graph.
- Workspace Settings modal.
- Confirm no standalone Sources route or navigation entry remains; configure a
  connector in Settings, select it in Ingest, and inspect resulting Raw material
  in Knowledge.

Review for:

- layout stability;
- no hidden expensive refresh;
- clear empty/error/loading states;
- readable report summaries before raw details;
- vault-aware state.

## Regression Risks

- UI drifting into a second backend implementation.
- Excessive page-load diagnostics.
- Components becoming too granular and hard to trace.
- Raw report payloads becoming the primary user experience.

## Release Evidence

For a 1.6 release note, mention:

- navigation and layout improvements;
- loading and diagnostics changes;
- report/diff readability improvements;
- component consolidation or component-library decision.

Verified 2026-07-18 for page-local vault and destination navigation:

- renderer i18n parity, TypeScript compilation, and production build passed;
- all 7 renderer Playwright cases passed, including page-local switching,
  retained Chat draft state, independent all-vault Chat scope, and explicit
  vault-scoped new Chat, hidden-token request gating, and exact run-citation
  resolution; the same suite confirms no Sources navigation remains while
  connector configuration is reachable in Settings and configured connectors
  remain selectable in Ingest;
- 51 focused UI/API surface tests passed;
- documentation governance, local links, architecture direction, and diff
  whitespace checks passed.

## Custom Input Error Verification

Renderer integration MUST submit custom text without a required model
configuration, keep the dialog open, and observe the mapped failure within the
dialog. Cancelling and reopening MUST not retain the old failure, and no second
copy may be visible at page level while the dialog is open.
