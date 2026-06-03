# Security Boundary

The `knoarbor-local` skill is retrieval-only.

## Allowed

- Call the local KnoArbor `/query` endpoint.
- Return page paths, summaries, excerpts, sources, gap signals, and context
  packs to the host AI.
- Run `scripts/query.py --check` to verify service connectivity.

## Not allowed

- Write, edit, delete, or rename wiki pages.
- Modify raw sources, config files, or the local vault.
- Read arbitrary local files outside what KnoArbor returns through `/query`.
- Present weak local matches as authoritative.
- Dump raw JSON to the end user unless explicitly requested.

## Privacy notes

Local wiki content may contain private notes, source paths, or project details.
The host AI should summarize only the evidence needed for the user's request and
cite page paths instead of exposing unnecessary raw context.

If the user asks for current facts, news, laws, prices, schedules, or other
time-sensitive information, use KnoArbor only as local memory/context and combine
it with current external tools.
