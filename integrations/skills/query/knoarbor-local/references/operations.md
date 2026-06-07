# KnoArbor Skill Operations

Use `scripts/knoarbor.py` from the skill directory. Do not rely on the
KnoArbor repository path. Global options come before the command:

```bash
python3 scripts/knoarbor.py --format json query "agent loop"
python3 scripts/knoarbor.py --format text query "agent loop"
```

Default output is concise plain text for host-AI tool use. Add
`--format json` before the command to return the underlying JSON response. The
skill does not write SQLite, CSV, or other derived files; durable reports and
indexes are managed by the KnoArbor service.

The helper needs Python 3.9 or newer. If Python is unavailable, use the direct
HTTP examples in `references/http-api.md`.

## Query

```bash
python3 scripts/knoarbor.py query "Agent Loop 是什么"
python3 scripts/knoarbor.py query "Agent Loop 控制模式" --mode deep --max-results 8
python3 scripts/knoarbor.py query "Agent Loop 页面全文" --context-format full --include-content
python3 scripts/knoarbor.py query "Agent Loop" --all-vaults
python3 scripts/knoarbor.py query "Agent Loop" --query-vault-id personal --query-vault-id team
```

Progressive retrieval behavior:

- Ordinary explanation: start with `balanced + compact`; answer from summaries,
  key points, and excerpts if the evidence is sufficient.
- Short lookup: keep result count small, usually 3-4.
- Detailed analysis, design review, or comparison: use `deep + compact` before
  reading full pages.
- Broad summary or comparison: aggregate the strongest relevant results instead
  of forcing one page to represent the whole answer.
- Multi-vault question: use `--all-vaults` when the user asks across local
  knowledge bases, or repeat `--query-vault-id` for a named subset.
- Multiple plausible candidates: list 2-5 candidate pages with title, path, and
  reason, then ask the user which one to expand.
- Explicit full-content request: prefer `page read` if a page path is known;
  otherwise query first, then read the selected page.
- Weak or missing local context: try one shorter or alternate query; if still
  weak, say that the local wiki lacks enough evidence.

Examples:

```bash
# Ordinary question: discover candidates and answer from compact evidence.
python3 scripts/knoarbor.py query "Agent Loop 是什么"

# Broad analysis: increase recall without loading full pages.
python3 scripts/knoarbor.py query "Agent Loop 和控制模式的设计取舍" --mode deep --max-results 8

# User asks which pages exist.
python3 scripts/knoarbor.py page list --contains "Agent Loop"

# User selects a page or asks for the full page.
python3 scripts/knoarbor.py page read concepts/Agent-Loop-and-Control-Patterns.md

# User selects a result from a multi-vault query.
python3 scripts/knoarbor.py --vault-id personal page read concepts/Agent-Loop-and-Control-Patterns.md
```

## Page Reading

```bash
python3 scripts/knoarbor.py page list
python3 scripts/knoarbor.py page list --dir concepts
python3 scripts/knoarbor.py page list --contains "Agent Loop"
python3 scripts/knoarbor.py page read concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py page links concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py --vault-id personal page read concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py --vault-id personal page links concepts/Agent-Loop-and-Control-Patterns.md
```

Use `page read` after query when the user asks to expand a specific result. Do
not rerun query just to read a known page path. For multi-vault query results,
reuse the result's `vault_id` with `--vault-id` so the selected page is read
from the same knowledge base.

## Ingest

```bash
python3 scripts/knoarbor.py ingest file /absolute/path/to/file.md
python3 scripts/knoarbor.py ingest folder /absolute/path/to/folder
python3 scripts/knoarbor.py ingest folder /absolute/path/to/folder --no-recursive
python3 scripts/knoarbor.py ingest connector codex
python3 scripts/knoarbor.py ingest connector codex claude_code
python3 scripts/knoarbor.py ingest connector --all
python3 scripts/knoarbor.py ingest recovery RUN_ID
```

Defaults are queued and write-enabled. Use only when the user explicitly asks to
compile, ingest, retry, or update the wiki.

`ingest folder` is for one-off folder paths. It does not edit persistent
configuration. Markdown files are ingested directly; non-Markdown files require
the user's configured document preprocessor.

## Lint

```bash
python3 scripts/knoarbor.py lint --mode deterministic --no-apply-safe-fixes --no-auto-apply-reviewed
python3 scripts/knoarbor.py lint --mode deterministic
python3 scripts/knoarbor.py lint --mode semantic_structural
python3 scripts/knoarbor.py lint --mode semantic_full --profile deep
python3 scripts/knoarbor.py lint --scope-page concepts/Agent-Loop-and-Control-Patterns.md
```

Use lint when the user asks to check, maintain, repair, or explain wiki quality.
For "check" or "diagnose" wording, use `--no-apply-safe-fixes
--no-auto-apply-reviewed` to keep the run read-only. For "fix", "repair", or
"maintain" wording, use the defaults so safe and reviewed changes can be
applied.

## Runs and Reports

```bash
python3 scripts/knoarbor.py runs list
python3 scripts/knoarbor.py runs list --all-vaults
python3 scripts/knoarbor.py runs get RUN_ID
python3 scripts/knoarbor.py runs events RUN_ID
python3 scripts/knoarbor.py runs cancel RUN_ID
python3 scripts/knoarbor.py report list
python3 scripts/knoarbor.py report list --all-vaults
python3 scripts/knoarbor.py report read maintenance/ingest_report_YYYYMMDD_HHMMSS.md
```

Use these when the user asks what happened, where a task is stuck, what changed,
or which pages were written. Use `--all-vaults` for list commands when the user
asks across configured knowledge bases. Use a single vault selector for
`runs get/events/cancel` and `report read` because run IDs and report paths are
vault-local.

## Diagnostics

```bash
python3 scripts/knoarbor.py check
python3 scripts/knoarbor.py doctor
python3 scripts/knoarbor.py doctor --connector codex
```

`check` is a fast service/vault probe. `doctor` performs readiness checks and is
better for setup or configuration questions.
