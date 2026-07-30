# Backup And Recovery

KnoArbor treats the runtime vault as user-owned data. The project repository
contains source code and public documentation; your local `vaults/`, `config.yaml`,
and `.env` are intentionally ignored by git.

This document explains what should be backed up, what can be recovered from git,
and what must never be overwritten by tests or release scripts.

Desktop data uses one platform-local root containing `config.yaml`, `vaults/`,
`state/`, `logs/`, `cache/`, and `tmp/`. Backup excludes disposable data only
at those canonical app-owned paths. A user source directory named `Cache`,
`logs`, or `tmp` remains durable vault content and is included.

## What To Back Up

Back up these files and directories if you want to preserve your local knowledge
base:

```text
config.yaml
.env
vaults/
```

Recommended backup scope:

- `vaults/default/wiki/`: maintained pages and readable source projections.
- `vaults/default/raw/`: copied inputs, normalized Markdown, source attachments, and source metadata.
- `vaults/default/artifacts/`: chat-generated images and other user-visible tool artifacts.
- `vaults/default/maintenance/`: human-readable workflow reports and archives.
- `vaults/default/.knoarbor/ingest.sqlite` and `.knoarbor/facts/`: transactional
  source heads, attempts, cursors, and immutable raw-grounded factual revisions.
  Back them up together.
- `vaults/default/.knoarbor/chat/`, `.knoarbor/memory/`, `.knoarbor/ledgers/`,
  and `.knoarbor/runs/`: optional continuity data when you want to preserve
  chat history, audit history, and run diagnostics. Incremental ingest cursors
  are already part of `ingest.sqlite`.
- `state/electron/`, `state/chat/sessions/`, `state/artifacts/`, and
  `state/ledgers/`: optional
  continuity, user-visible artifacts, and audit data for all-vault chat
  sessions.
- `config.yaml`: vault path, connector roots, model provider names, API keys,
  and runtime limits.
- `.env`: optional local development environment variables and other local
  secrets that are not part of model settings.

Rebuildable or disposable directories such as `.knoarbor/index/`,
`.knoarbor/locks/`, `.knoarbor/tmp/`, app `cache/`, app
`tmp/`, and app `state/` outside `state/electron/`, `state/chat/sessions/`,
`state/artifacts/`, and `state/ledgers/` are not core knowledge backups.

Keep `config.yaml` and `.env` in a secret manager or encrypted backup when
they contain secrets. Do not publish them.

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
uv run knoar ingest --vault vaults/default --rebuild-materialization
```

Because `vaults/` is ignored, restored files remain local runtime data and should
not be committed.

## Rebuild Indexes

If Markdown pages exist but the UI or query cannot see them, rebuild the human
and machine indexes:

```bash
uv run knoar ingest --vault vaults/default --rebuild-materialization
```

Then check:

```bash
uv run knoar --config config.yaml status --vault vaults/default
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
