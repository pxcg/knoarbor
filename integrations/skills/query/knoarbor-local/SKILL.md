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
- Expand/read a known result page -> `page read` with the returned page path.
- Inspect page relationships -> `page links`.
- Compile a specific file -> `ingest file`.
- Compile configured sources -> `ingest connector`.
- Check or maintain the wiki -> `lint`.
- Explain progress, failures, or outputs -> `runs ...` and `report ...`.
- Check readiness -> `doctor`; use `check` only for a fast service/vault probe.

Write operations (`ingest`, `lint`, `runs cancel`) require an explicit user
request to compile, maintain, retry, or cancel. Query and page reads are safe
read-only defaults.

## Main Helper

Prefer the bundled deterministic helper:

```bash
python3 scripts/knoarbor.py query "agent loop control patterns"
python3 scripts/knoarbor.py page read concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py page links concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py ingest file /absolute/path/to/file.md
python3 scripts/knoarbor.py ingest connector codex
python3 scripts/knoarbor.py lint --mode semantic_structural
python3 scripts/knoarbor.py runs list
python3 scripts/knoarbor.py report list
python3 scripts/knoarbor.py doctor
```

`scripts/query.py` remains as a compatibility wrapper for old query-only calls.

## Query Workflow

1. Rewrite the user request into a short standalone search query.
2. Run `scripts/knoarbor.py query ...` with default `--auto` unless exact
   settings are requested.
3. Read `results`, `context_pack`, `answer_guidance`, `gap_suggestions`, and
   `gaps`.
4. Use returned wiki context as local evidence, not as the final answer.
5. Cite concise page paths when local wiki evidence materially shapes the answer.
6. If matches are weak, say so and use another source or ask a clarifying
   question.

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

## References

Load only what is needed:

- `references/operations.md`: complete command map, modes, and examples.
- `references/security.md`: read/write boundaries and privacy rules.
- `references/troubleshooting.md`: service, vault, and query failures.
- `references/install.md`: install and smoke-test notes.

## Answer Rules

- Do not paste raw JSON unless asked.
- Do not present weak matches as authoritative.
- Do not fabricate wiki results.
- Do not read full wiki pages unless the user asks to inspect a page, asks to
  continue from a specific result, or a deep query lacks enough context.
- Do not write or modify wiki pages during ordinary query answering.
- For current facts, news, prices, laws, schedules, or other unstable topics,
  treat KnoArbor as local memory and combine it with current sources.
