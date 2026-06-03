---
name: knoarbor-local
description: Use when a user question may benefit from a local KnoArbor vault. Query the local /query endpoint for bounded wiki context, then let the host AI produce the final answer.
version: 1.0.0
author: KnoArbor contributors
license: Apache-2.0
metadata:
  tags: [knoarbor, wiki, knowledge-base, local-search, retrieval]
  category: query
---

# KnoArbor Local Query Skill

This skill connects a host AI assistant to a local KnoArbor service as a
retrieval-only knowledge source. KnoArbor returns page paths, summaries,
excerpts, context packs, retrieval trace, and gap signals. The host AI remains
responsible for final answers, synthesis, and user-facing judgment.

## When to Use

Use this skill when the user asks about:

- Personal notes, previous AI conversations, project notes, or knowledge already
  ingested into KnoArbor.
- Local wiki pages, source digests, concepts, entities, comparisons, workflows,
  retained queries, or page relationships.
- Questions where local knowledge should be checked before web search.
- Requests that mention KnoArbor, a local vault, local wiki, `wiki/`, or local
  project memory.

Do not use KnoArbor as the only source for current facts, news, prices,
schedules, laws, or other information likely to have changed recently. Use it as
local memory/context and combine it with current tools.

## Bundled Files

- `scripts/query.py`: standalone thin client for the local `/query` endpoint.
- `resources/example.env`: optional environment variable example.
- `resources/example-request.json`: stable `/query` request example.
- `resources/response-example.json`: compact response shape example.
- `resources/install.md`: installation and smoke-test notes.
- `resources/troubleshooting.md`: service, vault, and result troubleshooting.
- `resources/security.md`: retrieval-only safety boundary.

Load resource files only when the user asks for setup, troubleshooting, security,
or integration details.

## Query Workflow

1. Rewrite the user request into a short standalone search query.
2. Prefer `scripts/query.py`; it resolves local config and calls `/query`.
3. Keep helper default `--auto` behavior unless the user asks for exact query
   settings.
4. Read `results`, `context_pack`, `answer_guidance`, `gap_suggestions`, and
   `gaps`.
5. Use returned wiki context as local evidence, not as the final answer.
6. Cite relevant page paths when local wiki content materially shapes the answer.
7. If results are weak, say the local wiki has weak or no matching context and
   use another source or ask a clarifying question.

Do not call `/health` before every query. Use `scripts/query.py --check` or
`/health` only when setup is being tested or `/query` fails.

## Helper Commands

From this skill directory:

```bash
python3 scripts/query.py --check
python3 scripts/query.py "agent loop control patterns"
python3 scripts/query.py "逐段分析 Agent Loop 页面全文" --context-format full --include-content
```

The helper resolves the service and vault in this order:

1. CLI args: `--base-url`, `--vault`, `--config`.
2. Environment: `KNOARBOR_BASE_URL`, `KNOARBOR_VAULT_PATH`,
   `KNOARBOR_CONFIG_PATH`.
3. Runtime endpoint: `.knoarbor/endpoint.json` next to `config.yaml`.
4. `config.yaml` in the current working directory.
5. `~/Projects/KnoArbor/config.yaml`.

When KnoArbor starts with `knoar serve`, it writes the active endpoint to
`.knoarbor/endpoint.json`, so the helper can follow automatic port changes.

## Query Settings

Recommended modes:

- `quick`: title, tags, summary, and key points.
- `balanced`: default; bounded excerpts and 1-hop related expansion.
- `deep`: detailed local evidence. Prefer this before reading wiki files
  directly.

Recommended context formats:

- `compact`: default; bounded summaries, key points, excerpts, and context pack.
- `full`: full page bodies for matched pages. Use only when the user explicitly
  needs detailed page content.

The helper's default `--auto` behavior:

- ordinary explanation questions use `balanced + compact`;
- short lookup questions reduce result count;
- detailed analysis questions use `deep + compact`;
- explicit full-content requests use `deep + full`;
- broad recall requests may increase `max_results`.

Use `--no-auto` when exact manually supplied settings are required.

## Response Fields

Important fields:

- `results[].path`: wiki page path, suitable for citation.
- `results[].title`, `type`, `summary`, `key_points`, `excerpts`, `source`.
- `results[].match_kind`: retrieval origin only, not a citation permission flag.
- `context_pack`: evidence bundle for host AI synthesis.
- `answer_guidance`: safe-use guidance for retrieved evidence.
- `gap_suggestions` and `gaps`: missing or weak context signals.
- `retrieval_mode`, `stats`, `trace`: diagnostics for debugging.

If `page_dirs` is used, treat it as the initial direct search scope. Related
expansion may still return connected pages from other directories.

## Answer Rules

- Do not paste raw JSON to the user unless asked.
- Do not present weak matches as authoritative.
- Judge `direct` and `related` pages by relevance, excerpts, source, and the
  user's question.
- Do not write or modify wiki pages during query.
- Do not read full wiki files unless the user asks for detailed page inspection
  or `/query` returns insufficient context after a `deep` query.
- Prefer concise references such as `本地 wiki:
  concepts/Agent-Loop-and-Control-Patterns.md`.
- If local context conflicts with current external evidence, explain the conflict
  and prefer the source appropriate to the user's task.

## Failure Handling

If `/query` fails:

1. Run `python3 scripts/query.py --check`.
2. If the service is unavailable, say local wiki retrieval is unavailable.
3. Continue with the host AI's memory, project files, web search, or other tools
   as appropriate.

Do not fabricate wiki results.
