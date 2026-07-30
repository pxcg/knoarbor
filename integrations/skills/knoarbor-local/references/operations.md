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

## Natural Language To Command

Use these examples to map user phrasing to the smallest useful operation:

| User request | Command pattern |
| --- | --- |
| "我的 wiki 里有 Agent Loop 吗？" | `python3 scripts/knoarbor.py query "Agent Loop"` |
| "用我的本地知识库解释 Agent Loop" | `python3 scripts/knoarbor.py query "Agent Loop 是什么"` |
| "深入一点，比较 Agent Loop 和控制模式" | `python3 scripts/knoarbor.py query "Agent Loop 控制模式比较"` |
| "列出 Agent Loop 相关页面" | `python3 scripts/knoarbor.py page list --contains "Agent Loop"` |
| "打开刚才那个页面全文" | `python3 scripts/knoarbor.py --vault-id <result.vault_id> page read <result.path>` |
| "这个页面有哪些关联？" | `python3 scripts/knoarbor.py --vault-id <result.vault_id> page relations <result.path>` |
| "在所有知识库里查 iOS 音频检测" | `python3 scripts/knoarbor.py query "iOS 音频检测" --all-vaults` |
| "只查学习知识库和工程知识库" | `python3 scripts/knoarbor.py query "主题" --query-vault-id rag-llm-learning --query-vault-id agent-engineering` |
| "刚才查到的 team 知识库页面展开一下" | `python3 scripts/knoarbor.py --vault-id team page read <result.path>` |
| "我有哪些知识库可以查？" | `python3 scripts/knoarbor.py vaults list` |
| "把这个 Markdown 文件加入知识库" | `python3 scripts/knoarbor.py ingest file /absolute/path/to/file.md` |
| "编译这个资料文件夹" | `python3 scripts/knoarbor.py ingest folder /absolute/path/to/folder` |
| "同步 Codex/Claude 聊天记录" | `python3 scripts/knoarbor.py ingest connector codex claude_code` |
| "KnoArbor 支持哪些资料来源？" | `python3 scripts/knoarbor.py sources catalog` |
| "Codex 来源怎么配置？" | `python3 scripts/knoarbor.py --format json sources catalog --connector codex` |
| "检查知识库有没有问题" | `python3 scripts/knoarbor.py lint --mode deterministic` |
| "分析这个知识库的质量" | `python3 scripts/knoarbor.py lint --mode semantic` |
| "刚才运行到哪了？" | `python3 scripts/knoarbor.py runs list` then `python3 scripts/knoarbor.py runs get RUN_ID` |
| "为什么失败？看报告" | `python3 scripts/knoarbor.py report list` then `python3 scripts/knoarbor.py report read <report.path>` |
| "这次写入了哪些页面？" | `python3 scripts/knoarbor.py report read <report.path>` |
| "最近有哪些运行记录？" | `python3 scripts/knoarbor.py runs list --all-vaults` |
| "重试失败的 ingest" | `python3 scripts/knoarbor.py ingest recovery RUN_ID` |
| "KnoArbor 配好了吗？" | `python3 scripts/knoarbor.py doctor` |

For write workflows, include global `--vault-id <id>` when the user names a
configured knowledge base. Query may span multiple vaults; ingest and lint write
to one vault per run.

## Query

```bash
python3 scripts/knoarbor.py query "Agent Loop 是什么"
python3 scripts/knoarbor.py query "Agent Loop 控制模式"
python3 scripts/knoarbor.py query "Agent Loop" --all-vaults
python3 scripts/knoarbor.py query "Agent Loop" --query-vault-id personal --query-vault-id team
python3 scripts/knoarbor.py page read Agent-Loop.md
```

Progressive retrieval behavior:

- Ordinary explanation: use a compact query and answer only from selected raw
  evidence when coverage is sufficient.
- Short lookup: state the target precisely.
- Detailed analysis, design review, or comparison: state every required
  dimension in the query before reading full pages.
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
python3 scripts/knoarbor.py query "Agent Loop 和控制模式的设计取舍"

# User asks which pages exist.
python3 scripts/knoarbor.py page list --contains "Agent Loop"

# User selects a page or asks for the full page.
python3 scripts/knoarbor.py page read Agent-Loop-and-Control-Patterns.md

# User selects a result from a multi-vault query.
python3 scripts/knoarbor.py --vault-id personal page read Agent-Loop-and-Control-Patterns.md
```

## Page Reading

```bash
python3 scripts/knoarbor.py page list
python3 scripts/knoarbor.py page list --dir pages
python3 scripts/knoarbor.py page list --contains "Agent Loop"
python3 scripts/knoarbor.py page read Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py page relations Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py --vault-id personal page read Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py --vault-id personal page relations Agent-Loop-and-Control-Patterns.md
```

Use `page read` after query when the user asks to expand a specific result. Do
not rerun query just to read a known page path. For multi-vault query results,
reuse the result's `vault_id` with `--vault-id` so the selected page is read
from the same knowledge base.

## Vaults

```bash
python3 scripts/knoarbor.py vaults list
python3 scripts/knoarbor.py --format json vaults list
```

Use `vaults list` when the user asks which knowledge bases are available, or
when a follow-up question names a knowledge base that has not yet been
resolved. Prefer the returned `vault_id` for later `query`, `page`, `runs`,
`reports`, `ingest`, and `lint` commands.

## Ingest

```bash
python3 scripts/knoarbor.py ingest file /absolute/path/to/file.md
python3 scripts/knoarbor.py ingest folder /absolute/path/to/folder
python3 scripts/knoarbor.py ingest folder /absolute/path/to/folder --no-recursive
python3 scripts/knoarbor.py ingest connector codex
python3 scripts/knoarbor.py ingest connector codex claude_code
python3 scripts/knoarbor.py ingest connector --all
python3 scripts/knoarbor.py --vault-id personal ingest connector codex
python3 scripts/knoarbor.py ingest recovery RUN_ID
```

Defaults are queued and write-enabled. Use only when the user explicitly asks to
compile, ingest, retry, or update the wiki.

`ingest folder` is for one-off folder paths. It does not edit persistent
configuration. Markdown files are ingested directly; non-Markdown files require
the user's configured document preprocessor.

When the user names a configured knowledge base, pass it with global
`--vault-id <id>`. Ingest writes to one vault per run; do not use multi-vault
query flags for write workflows.

## Source Catalog

```bash
python3 scripts/knoarbor.py sources catalog
python3 scripts/knoarbor.py sources catalog --connector markdown
python3 scripts/knoarbor.py --format json sources catalog --connector codex
```

Use this when the user asks which input sources are supported, which connectors
are enabled, or what settings a connector accepts. This command reads connector
capabilities only; it does not scan local files and does not start ingest.

## Lint

```bash
python3 scripts/knoarbor.py lint --mode deterministic
python3 scripts/knoarbor.py lint --mode semantic
python3 scripts/knoarbor.py lint --scope-page Agent-Loop-and-Control-Patterns.md
python3 scripts/knoarbor.py --vault-id personal lint --mode semantic
```

Use lint when the user asks to check, repair, or explain wiki quality. Semantic
models produce evidence-backed findings; lint automatically executes approved
repairs through ingest or materialization and records a post-repair scan.

Like ingest, lint maintains one vault per run. Use global `--vault-id <id>` when
the user names a configured knowledge base.

## Runs and Reports

```bash
python3 scripts/knoarbor.py runs list
python3 scripts/knoarbor.py runs list --all-vaults
python3 scripts/knoarbor.py runs get RUN_ID
python3 scripts/knoarbor.py runs events RUN_ID
python3 scripts/knoarbor.py runs cancel RUN_ID
python3 scripts/knoarbor.py report list
python3 scripts/knoarbor.py report list --all-vaults
python3 scripts/knoarbor.py report read maintenance/reports/ingest/ingest_report_YYYYMMDD_HHMMSS.md
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
