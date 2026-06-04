---
name: knoarbor-local
description: "Use when a user request may benefit from a local KnoArbor vault: query local wiki context, read known pages, inspect links/reports/runs, diagnose the service, or explicitly compile/maintain the wiki through KnoArbor APIs."
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

## Core Rule

Use the smallest operation that satisfies the user request:

- Knowledge question -> `query`.
- Page discovery -> `page list`.
- Expand/read a known result page -> `page read` with the returned page path.
- Inspect page relationships -> `page links`.
- Compile a specific file -> `ingest file`.
- Compile a one-off folder -> `ingest folder`.
- Compile configured sources -> `ingest connector`.
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
- "What links to this?", "why is this page connected?", "show relationships" ->
  `page links`.
- "What pages do I have about X?", "list concept pages", "find pages named X" ->
  `page list`.
- "Compile this file/folder", "add this note/PDF/folder to my wiki", "ingest
  these materials" -> `ingest file` or `ingest folder`.
- "Update from Codex/Hermes/Claude/OpenClaw history", "sync my configured
  sources" -> `ingest connector`.
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
python3 scripts/knoarbor.py page list --contains "agent loop"
python3 scripts/knoarbor.py page read concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py page links concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py ingest file /absolute/path/to/file.md
python3 scripts/knoarbor.py ingest folder /absolute/path/to/folder
python3 scripts/knoarbor.py ingest connector codex
python3 scripts/knoarbor.py lint --mode semantic_structural
python3 scripts/knoarbor.py runs list
python3 scripts/knoarbor.py report list
python3 scripts/knoarbor.py doctor
```

Path rules:

- Run commands from this skill directory, or call `scripts/knoarbor.py` through
  a path relative to this skill directory.
- Do not assume the current working directory is the KnoArbor repository.
- Do not hard-code the user's local KnoArbor project path.
- The helper uses only the Python standard library and loads sibling files
  through `__file__`.
- The helper requires Python 3.9 or newer.

Fallback rules:

- If `python3` is unavailable, use `references/http-api.md` with `curl` or the
  host tool's HTTP client.
- If the helper cannot discover the service, run `python3 scripts/knoarbor.py
  check` and follow the reported service or vault diagnostics.
- HTTP-only callers should use `GET /runtime` after the service URL is known.
  If the service URL is unknown and local files are readable, use
  `.knoarbor/endpoint.json` next to `config.yaml`.
- If the local service is unavailable, report that KnoArbor is unavailable and
  continue with other available context. Do not fabricate wiki results.

## Output Formats

The helper defaults to concise plain text because host AI tools usually need a
small, readable tool result. Use `--format json` before the command when
structured JSON is needed for debugging or automation:

```bash
python3 scripts/knoarbor.py --format json query "agent loop"
python3 scripts/knoarbor.py --format json page read concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py --format text query "agent loop"
```

Do not ask the helper to create SQLite or other local data files. Persistent
indexes, ledgers, and reports belong to the KnoArbor service and vault, not to
the portable skill bundle.

## Progressive Retrieval Policy

Use query as candidate discovery, not as the final answer shape. Prefer this
flow:

1. Rewrite the user request into a short standalone search query.
2. Start with `scripts/knoarbor.py query ...` using default `--auto` unless the
   user requested exact settings.
3. Inspect `results`, `excerpts`, `context_pack`, `answer_guidance`,
   `gap_suggestions`, and `gaps`.
4. If one or a few results clearly answer the question, answer from summaries,
   key points, and excerpts. Cite concise page paths.
5. If evidence is relevant but thin, run a deeper compact query or read only the
   1-2 strongest pages with `page read`.
6. If the user asks for a broad summary, overview, or comparison, aggregate the
   strongest relevant results instead of forcing a single page.
7. If several candidates are plausible and the user's intent is ambiguous, list
   2-5 candidates with title, path, and reason, then ask the user to choose.
8. If matches are weak, try a shorter or alternate query once. If still weak,
   say the local wiki does not contain enough evidence and ask a clarifying
   question or use another source.

Do not treat compact context as a user-facing answer by itself. Compact context
is the default evidence layer for the host AI to judge relevance. Full page
content is a drilldown step.

### When To Read Full Pages

Use `page read` when:

- the user gives a page path or selects a previous result;
- the user asks for a full page, original text, detailed page analysis, or
  section-by-section review;
- query returns a clear direct match, but excerpts are not enough for the
  requested depth;
- the task needs page structure, exact wording, frontmatter, tables, or long
  lists.

Do not automatically read many pages in full. When more than 2-3 pages may be
needed, list candidates first and let the user pick a scope.

Do not call `/health` before every query. Use `scripts/knoarbor.py check` only
when setup is being tested or a request fails.

## Response Use

Important query fields:

- `results[].path`: stable page path for citation or `page read`.
- `results[].summary`, `key_points`, `excerpts`, `source`: local evidence.
- `results[].match_kind`: retrieval origin only; judge relevance yourself.
- `context_pack`: compact evidence bundle for synthesis.
- `gaps` and `gap_suggestions`: weak or missing local context signals.

If `page_dirs` is used, it limits only the first search scope; related expansion
may still return connected pages from other directories.

For broad design, review, or comparison tasks, use `deep + compact` before
reading full pages. For explicit full-content requests, prefer `page read` when
the target page path is known; otherwise query first, then read the selected
page.

Evidence synthesis:

- Cite concise page paths near important claims.
- Treat KnoArbor as local memory. For unstable current facts, newer external
  sources can override older wiki pages.
- If wiki evidence conflicts with current sources or with another wiki page,
  state the conflict instead of silently merging both.
- Use source digest pages as provenance, not as a replacement for the generated
  concept/entity/comparison/query pages.

## References

Load only what is needed:

- `references/operations.md`: complete command map, modes, and examples.
- `references/security.md`: read/write boundaries and privacy rules.
- `references/troubleshooting.md`: service, vault, and query failures.
- `references/http-api.md`: direct `curl` examples for environments without
  Python or when the host tool uses an HTTP client instead of shell commands.

## Answer Rules

- Do not paste JSON unless asked.
- Do not present weak matches as authoritative.
- Do not fabricate wiki results.
- Do not read full wiki pages unless the user asks to inspect a page, asks to
  continue from a specific result, or a deep query lacks enough context.
- Do not write or modify wiki pages during ordinary query answering.
- For current facts, news, prices, laws, schedules, or other unstable topics,
  treat KnoArbor as local memory and combine it with current sources.
