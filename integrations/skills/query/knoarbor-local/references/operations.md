# KnoArbor Skill Operations

Use `scripts/knoarbor.py` from the skill directory. Global options come before
the command:

```bash
python3 scripts/knoarbor.py --base-url http://127.0.0.1:8000 --vault /path/to/wiki query "agent loop"
python3 scripts/knoarbor.py --config /path/to/config.yaml doctor
python3 scripts/knoarbor.py --raw query "agent loop"
```

## Query

```bash
python3 scripts/knoarbor.py query "Agent Loop 是什么"
python3 scripts/knoarbor.py query "Agent Loop 控制模式" --mode deep --max-results 8
python3 scripts/knoarbor.py query "Agent Loop 页面全文" --context-format full --include-content
```

Recommended behavior:

- Ordinary explanation: `balanced + compact`.
- Short lookup: keep result count small.
- Detailed analysis: `deep + compact`.
- Explicit full-content request: prefer `page read` if a page path is known;
  otherwise use `deep + full`.

## Page Reading

```bash
python3 scripts/knoarbor.py page list
python3 scripts/knoarbor.py page list --dir concepts
python3 scripts/knoarbor.py page list --contains "Agent Loop"
python3 scripts/knoarbor.py page read concepts/Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py page links concepts/Agent-Loop-and-Control-Patterns.md
```

Use `page read` after query when the user asks to expand a specific result. Do
not rerun query just to read a known page path.

## Ingest

```bash
python3 scripts/knoarbor.py ingest file /absolute/path/to/file.md
python3 scripts/knoarbor.py ingest connector codex
python3 scripts/knoarbor.py ingest connector codex claude_code
python3 scripts/knoarbor.py ingest connector --all
python3 scripts/knoarbor.py ingest recovery RUN_ID
```

Defaults are queued and write-enabled. Use only when the user explicitly asks to
compile, ingest, retry, or update the wiki.

## Lint

```bash
python3 scripts/knoarbor.py lint --mode deterministic
python3 scripts/knoarbor.py lint --mode semantic_structural
python3 scripts/knoarbor.py lint --mode semantic_full --profile deep
python3 scripts/knoarbor.py lint --scope-page concepts/Agent-Loop-and-Control-Patterns.md
```

Use lint when the user asks to check, maintain, repair, or explain wiki quality.

## Runs and Reports

```bash
python3 scripts/knoarbor.py runs list
python3 scripts/knoarbor.py runs get RUN_ID
python3 scripts/knoarbor.py runs events RUN_ID
python3 scripts/knoarbor.py runs cancel RUN_ID
python3 scripts/knoarbor.py report list
python3 scripts/knoarbor.py report read maintenance/ingest_report_YYYYMMDD_HHMMSS.md
```

Use these when the user asks what happened, where a task is stuck, what changed,
or which pages were written.

## Diagnostics

```bash
python3 scripts/knoarbor.py check
python3 scripts/knoarbor.py doctor
python3 scripts/knoarbor.py doctor --connector codex
```

`check` is a fast service/vault probe. `doctor` performs readiness checks and is
better for setup or configuration questions.
