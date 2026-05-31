---
name: knoarbor-local
description: Use when a user question may benefit from a local KnoArbor vault. Query the local /query/search endpoint for bounded wiki context, then let the host AI produce the final answer.
version: 1.0.0
author: KnoArbor contributors
license: Apache-2.0
metadata:
  tags: [knoarbor, wiki, knowledge-base, local-search, obsidian]
  category: query
---

# KnoArbor Local Query Skill

This skill connects a host AI assistant to a local KnoArbor service as a retrieval-only knowledge source.

KnoArbor returns context, evidence, page paths, retrieval trace, and gap signals. The host AI remains responsible for final answers, synthesis, tool coordination, and user-facing judgment.

## When to Use

Use this skill when the user asks about:

- Personal notes, previous AI conversations, or knowledge already ingested into KnoArbor.
- Local wiki pages, page relationships, source digests, concepts, entities, comparisons, workflows, or retained queries.
- Questions where local knowledge should be checked before web search.
- Requests that mention KnoArbor, Obsidian vault, local wiki, `wiki/`, or project notes.

Do not use this as the only source when the user asks for current facts, news, prices, schedules, laws, or other information likely to have changed recently. In those cases, use KnoArbor as memory/context and combine it with current tools.

## Configuration

Set these values according to the user's local deployment:

```text
KNOARBOR_BASE_URL=http://127.0.0.1:8000
KNOARBOR_VAULT_PATH=/absolute/path/to/wiki
```

The query endpoint is `${KNOARBOR_BASE_URL}/query/search`.

If the service is unavailable, tell the user that local wiki retrieval is currently unavailable and continue with other available tools.

## Query Workflow

1. Rewrite the user request into a short standalone search query.
2. Prefer the bundled helper script `scripts/query.py` when available. It resolves local config and calls `/query/search`.
3. If the helper is not available, call `/query/search` directly with `mode: "balanced"` unless the user needs a quick lookup or deep evidence.
4. Read `results`, `context_pack`, `answer_guidance`, `gap_suggestions`, and `gaps`.
5. Use the returned wiki context as local evidence, not as the final answer.
6. Cite relevant page paths when local wiki content materially shapes the answer.
7. If results are weak, say the local wiki has weak or no matching context and use another tool or ask a clarifying question.

Do not call `/health` before every query. Use `/health` only when `/query/search` fails or times out.

## Request Shape

Use a JSON body like:

```json
{
  "query": "agent loop control patterns",
  "obsidian_vault_path": "/absolute/path/to/wiki",
  "max_results": 6,
  "mode": "balanced",
  "include_related": true
}
```

Recommended modes:

- `quick`: title, tags, summary, and key points only.
- `balanced`: default; includes bounded excerpts and 1-hop related page expansion.
- `deep`: use only when the user needs detailed local evidence. Prefer `deep` before reading wiki files directly.

## Example Command

Use the helper script from this skill directory:

```bash
python3 scripts/query.py "agent loop control patterns" --mode balanced --max-results 6
```

The helper reads configuration in this order:

1. `--base-url`, `--vault`, and `--config` arguments.
2. `KNOARBOR_BASE_URL`, `KNOARBOR_VAULT_PATH`, and `KNOARBOR_CONFIG_PATH`.
3. `config.yaml` in the current working directory.
4. `~/Projects/KnoArbor/config.yaml`.

For Chinese questions, keep the original Chinese query unless an English technical term is clearly better.

## Response Fields

Important fields:

- `results[].path`: wiki page path, suitable for citation.
- `results[].title`: page title.
- `results[].type`: page type.
- `results[].match_kind`: retrieval origin only. `direct` matched the query in the initial search scope; `related` was reached through wiki links from a direct match. This is not a citation permission flag.
- `results[].summary`: compact page summary.
- `results[].key_points`: reusable page points.
- `results[].excerpts`: bounded matching snippets.
- `results[].related_pages`: linked pages returned for context.
- `results[].source`: raw source or source digest pointer.
- `answer_guidance`: instructions for using retrieved evidence safely.
- `gap_suggestions`: report-only signals for no-result or low-confidence retrieval.
- `context_pack`: compact evidence bundle for host AI synthesis.
- `retrieval_mode`: local retrieval strategy used by the service.
- `gaps`: retrieval limitations or missing context.

If the request uses `page_dirs`, treat it as the initial direct search scope. Related expansion may still return pages from other directories when those pages are connected through the wiki graph.

## Answer Rules

- Do not paste raw JSON to the user unless asked.
- Do not present weak matches as authoritative.
- Do not assume `direct` pages are always more cite-worthy than `related` pages. Judge every returned page by relevance, excerpts, source, and the user's question.
- Do not write or modify wiki pages during query.
- Do not read full wiki files unless the user asks for detailed page inspection or `/query/search` returns insufficient context after a `deep` query.
- Prefer concise references such as `本地 wiki: concepts/Agent-Loop-and-Control-Patterns.md`.
- If local context conflicts with current external evidence, explain the conflict and prefer the source appropriate to the user's task.

## Failure Handling

If `/query/search` fails:

1. Check whether FastAPI is running at `http://127.0.0.1:8000/health`.
2. If it is not running, state that local wiki search is unavailable.
3. Continue with the host AI's memory, project files, web search, or other available tools as appropriate.

Do not fabricate wiki results.
