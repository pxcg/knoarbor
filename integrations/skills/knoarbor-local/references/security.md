# Security Boundary

The `knoarbor-local` skill is read-first. Query and page-reading operations are
safe defaults. Write operations are available only when the user explicitly asks
to compile, maintain, retry, or cancel a run.

## Allowed

- Call the local KnoArbor `/query` endpoint.
- Read maintained wiki pages through `/wiki/pages/content`.
- Inspect runs, reports, diagnostics, and wiki links.
- Return page paths, summaries, excerpts, sources, gap signals, and context
  packs to the host AI.
- Run `scripts/knoarbor.py check` to verify service connectivity.
- Trigger `/ingest` or `/lint` only when requested by the user.

## Not allowed

- Write, edit, delete, or rename wiki pages outside KnoArbor ingest/lint APIs.
- Modify raw sources, config files, or the local vault.
- Read arbitrary local files outside what KnoArbor returns through its API.
- Present weak local matches as authoritative.
- Dump JSON to the end user unless explicitly requested.
- Run large all-connector ingest unless the user explicitly asks for it.

## Privacy notes

Local wiki content may contain private notes, source paths, or project details.
The host AI should summarize only the evidence needed for the user's request and
cite page paths instead of exposing unnecessary raw context.

If the user asks for current facts, news, laws, prices, schedules, or other
time-sensitive information, use KnoArbor only as local memory/context and combine
it with current external tools.
