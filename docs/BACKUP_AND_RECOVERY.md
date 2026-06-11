# Backup And Recovery

KnoArbor treats the runtime vault as user-owned data. The project repository
contains source code and public documentation; your local `vaults/`, `config.yaml`,
and `.env` are intentionally ignored by git.

This document explains what should be backed up, what can be recovered from git,
and what must never be overwritten by tests or release scripts.

## What To Back Up

Back up these files and directories if you want to preserve your local knowledge
base:

```text
config.yaml
.env
vaults/
```

Recommended backup scope:

- `vaults/**/*.md`: maintained wiki pages and reports.
- `vaults/all/.knoarbor/`: machine indexes, ledgers, run records, and locks.
- `vaults/all/raw/`: copied or normalized raw sources if you choose to keep them.
- `config.yaml`: vault path, connector roots, model provider names, and runtime
  limits.
- `.env`: model provider API keys and other local secrets.

Keep `.env` in a secret manager or encrypted backup. Do not publish it.

## What Git Can Recover

Git can recover only files that were previously tracked by git. In normal
KnoArbor usage, runtime vault data is ignored and therefore not recoverable from
git.

Git can help when:

- a file was tracked in the repository before it was removed;
- a release tag or branch contains the old version;
- you intentionally committed an example or fixture.

Git cannot recover:

- ignored `vaults/` runtime pages that were never committed;
- ignored `config.yaml` or `.env`;
- local connector source files outside the repository;
- deleted files that have no filesystem backup.

## Safe Recovery From Git

When recovering old tracked files, restore into a temporary directory first when
possible:

```bash
mkdir -p .local-dev/recovered-vault
git archive <commit> vaults | tar -x -C .local-dev/recovered-vault
```

After reviewing the recovered files, copy only the pages you want into your
runtime vault.

If you explicitly decide to restore tracked wiki files directly into the current
vault, use a known commit:

```bash
git restore --source=<commit> --worktree -- vaults
uv run python - <<'PY'
from pathlib import Path
from knoarbor.storage import update_index
update_index(Path("vaults/all"))
PY
```

Because `vaults/` is ignored, restored files remain local runtime data and should
not be committed.

## Rebuild Indexes

If Markdown pages exist but the UI or query cannot see them, rebuild the human
and machine indexes:

```bash
uv run python - <<'PY'
from pathlib import Path
from knoarbor.storage import update_index
update_index(Path("vaults/all"))
PY
```

Then check:

```bash
uv run knoar --config config.yaml status --vault vaults/all
uv run knoar --config config.yaml query "agent loop" --json
```

## Runtime Data Isolation Rule

Tests, release checks, smoke tests, and development gates must not operate on a
maintainer's real runtime vault by default.

Required rule:

- Use `mktemp -d` for test vaults and test configs.
- Use `config.example.yaml` as input, then rewrite paths into the temporary
  directory.
- Clean temporary directories with `trap`.
- Do not run automated tests against project-root `vaults/`, `config.yaml`, or
  `.env`.
- Do not use broad cleanup commands such as `git clean -fdx` or `rm -rf` against
  ignored project-root runtime paths.

Only explicit user-facing commands or UI actions should operate on the configured
real vault.

## Recommended Personal Backup Strategy

For local use:

- Keep `vaults/` in Time Machine, Syncthing, cloud backup, or another private
  backup system.
- Keep `.env` in a password manager or encrypted vault.
- Export occasional snapshots before large ingest/lint runs.
- Do not rely on the public git repository to preserve your local knowledge base.

For team use:

- Store shared runtime vaults in a private repository or private object storage
  only after privacy review.
- Keep raw private sources separate from public project code.
- Document who can access model provider logs and generated wiki pages.
