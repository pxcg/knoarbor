---
name: knoarbor-local
description: "Use when a user request may benefit from a local KnoArbor vault: query local wiki context, read known pages, inspect page relations/reports/runs, diagnose the service, or explicitly compile/maintain the wiki through KnoArbor APIs."
license: Apache-2.0
metadata:
  tags: [knoarbor, wiki, knowledge-base, local-search, retrieval]
  category: knowledge
---

# KnoArbor Local

Connects a host AI assistant to a local KnoArbor service. KnoArbor provides local
wiki retrieval, page reading, ingest, lint, diagnostics, reports, and run
monitoring. The host AI still writes the final answer and decides how to use the
evidence.

This skill is evidence-first. For ordinary host-AI conversations, use
`query`, `page read`, `report read`, and related operations so the host AI can
compose the final answer. The KnoArbor `/chat` API is the local console's
bounded Wiki Chat Agent; do not call it by default from this skill because that
would delegate answer synthesis to a second assistant. Use `/chat` only when the
user explicitly asks to invoke the KnoArbor console chat behavior.

## Core Rule

Use the smallest operation that satisfies the user request:

- Knowledge question -> `query`.
- Page discovery -> `page list`.
- Vault discovery -> `vaults list`.
- Expand/read a known result page -> `page read` with the returned page path.
- Inspect page relationships -> `page relations`.
- Compile a specific file -> `ingest file`.
- Compile a one-off folder -> `ingest folder`.
- Compile configured sources -> `ingest connector`.
- Inspect supported source connectors -> `sources catalog`.
- Check or maintain the wiki -> `lint`.
- Explain progress, failures, or outputs -> `runs ...` and `report ...`.
- Check readiness -> `doctor`; use `check` only for a fast service/vault probe.

Write operations (`ingest`, `lint`, `runs cancel`) require an explicit user
request to compile, maintain, retry, or cancel. Query and page reads are safe
read-only defaults.

Do not use KnoArbor when the request is fully answerable from the current
conversation, local repository files already in context, or a current external
source, and no local wiki memory is needed.

## Intent Map

Map natural user requests to operations before choosing a command:

- "What is X?", "explain X from my wiki", "do I have notes about X" -> `query`.
- "Show the full page", "continue from this result", "open this wiki page" ->
  `page read`.
- "What relates to this page?", "why is this page connected?", "show relationships" ->
  `page relations`.
- "What pages do I have about X?", "list wiki pages", "find pages named X" ->
  `page list`.
- "Which knowledge bases do I have?", "what vaults are available", "我有哪些知识库" ->
  `vaults list`.
- "Compile this file/folder", "add this note/PDF/folder to my wiki", "ingest
  these materials" -> `ingest file` or `ingest folder`.
- "Update from Codex/Hermes/Claude/OpenClaw history", "sync my configured
  sources" -> `ingest connector`.
- "What sources does KnoArbor support?", "which connectors are enabled?", "how
  can I configure sources?" -> `sources catalog`.
- "What happened in the last run?", "which pages were written?", "why did it
  fail?", "show the report" -> `runs ...` and `report ...`.
- "Retry failed ingest", "rerun failed items" -> `ingest recovery`.
- "Check the wiki", "diagnose wiki quality", "scan for problems" -> `lint`
  with no-apply flags.
- "Fix the wiki", "repair broken links", "maintain the wiki", "run
  governance" -> `lint` with default maintenance behavior.
- "Is KnoArbor ready?", "why can't the skill connect?", "check my setup" ->
  `doctor` or `check`.

## Execution Contract

Use the bundled helper first:

```bash
python3 scripts/knoarbor.py query "agent loop control patterns"
python3 scripts/knoarbor.py --vault-id personal query "agent loop control patterns"
python3 scripts/knoarbor.py query "agent loop control patterns" --all-vaults
python3 scripts/knoarbor.py query "agent loop control patterns" --query-vault-id personal --query-vault-id team
python3 scripts/knoarbor.py page list --contains "agent loop"
python3 scripts/knoarbor.py page read Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py --vault-id personal page read Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py page relations Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py vaults list
python3 scripts/knoarbor.py sources catalog
python3 scripts/knoarbor.py sources catalog --connector codex
python3 scripts/knoarbor.py ingest file /absolute/path/to/file.md
python3 scripts/knoarbor.py ingest folder /absolute/path/to/folder
python3 scripts/knoarbor.py ingest connector codex
python3 scripts/knoarbor.py lint --mode semantic_structural
python3 scripts/knoarbor.py runs list
python3 scripts/knoarbor.py runs list --all-vaults
python3 scripts/knoarbor.py report list
python3 scripts/knoarbor.py report list --all-vaults
python3 scripts/knoarbor.py doctor
```

Path rules:

- Run commands from this skill directory, or call `scripts/knoarbor.py` through
  a path relative to this skill directory.
- Do not assume the current working directory is the KnoArbor repository.
- Do not hard-code the user's local KnoArbor project path.
- The helper uses only the Python standard library and is safe to run from any
  current working directory when addressed by its skill-relative path.
- The helper requires Python 3.9 or newer.
- Use `--vault-id <id>` when the whole operation targets one configured
  knowledge base.
- Use `query --all-vaults` when a knowledge question should search all
  configured knowledge bases.
- Use repeated `query --query-vault-id <id>` flags when the user names a
  specific subset of knowledge bases.
- Use `check` first if the available vault IDs are unknown.

Fallback rules:

- If `python3` is unavailable, use `references/http-api.md` with `curl` or the
  host tool's HTTP client.
- If the helper cannot discover the service, run `python3 scripts/knoarbor.py
  check` and follow the reported service or vault diagnostics.
- The helper first checks the user-level runtime endpoint written by
  `knoar serve`, then project-local config and endpoint files, then `/runtime`.
  This allows discovery when the service auto-selects a port other than 8000.
- HTTP-only callers should use `GET /runtime` after the service URL is known.
  If the service URL is unknown and local files are readable, use the
  user-level `.knoarbor/endpoint.json` or the project-local endpoint next to
  `config.yaml`.
- If the local service is unavailable, report that KnoArbor is unavailable and
  continue with other available context. Do not fabricate wiki results.
- If a vault ID is invalid, use `check` to list available vault IDs and retry
  with one of those IDs.

## Output Formats

The helper defaults to concise plain text because host AI tools usually need a
small, readable tool result. Use `--format json` before the command when
structured JSON is needed for debugging or automation:

```bash
python3 scripts/knoarbor.py --format json query "agent loop"
python3 scripts/knoarbor.py --format json page read Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py --format text query "agent loop"
```

Do not ask the helper to create SQLite or other local data files. Persistent
indexes, ledgers, and reports belong to the KnoArbor service and vault, not to
the portable skill bundle.

## Progressive Retrieval Policy

Use query as candidate discovery, not as the final answer shape. Start with a
compact query, answer from summaries/excerpts when sufficient, and read full
pages only when the user asks for depth or selects a specific result.

When a query result includes `vault_id`, reuse it for follow-up reads:

```bash
python3 scripts/knoarbor.py --vault-id <result.vault_id> page read <result.path>
python3 scripts/knoarbor.py --vault-id <result.vault_id> page relations <result.path>
```

Do not call `/health` before every query. Use `scripts/knoarbor.py check` only
when setup is being tested or a request fails.

For detailed retrieval behavior, read `references/retrieval.md`.

## References

Load only what is needed:

- `references/operations.md`: complete command map, modes, and examples.
- `references/retrieval.md`: progressive retrieval, full-page reading, and
  evidence synthesis rules.
- `references/security.md`: read/write boundaries and privacy rules.
- `references/troubleshooting.md`: service, vault, and query failures.
- `references/http-api.md`: direct `curl` examples for environments without
  Python or when the host tool uses an HTTP client instead of shell commands.

## Response Rules

- Do not paste JSON unless asked.
- Do not present weak matches as authoritative.
- Do not fabricate wiki results.
- Do not read full wiki pages unless the user asks to inspect a page, asks to
  continue from a specific result, or a deep query lacks enough context.
- Do not write or modify wiki pages during ordinary query answering.
- For current facts, news, prices, laws, schedules, or other unstable topics,
  treat KnoArbor as local memory and combine it with current sources.
