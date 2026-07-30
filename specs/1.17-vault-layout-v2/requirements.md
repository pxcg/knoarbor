# Vault Layout v2 Requirements

## Status

Accepted baseline with the factual-revision layout amendment implemented and
verified with the owning ingest specifications.

## Goal

KnoArbor vaults must separate human-readable wiki content from raw inputs, run reports, and machine runtime state. A user should be able to open the wiki layer in Obsidian without seeing ledgers, checkpoints, queues, locks, or maintenance artifacts.

## Requirements

- A vault root contains three visible top-level areas:
  - `raw/`: original or normalized input material.
  - `wiki/`: human-facing wiki publication layer.
  - `maintenance/`: human-readable operational reports and archives.
- `wiki/` contains only user-readable wiki material:
  - `wiki/pages/`: current deterministic source projections and maintained pages.
  - `wiki/sources/`: reserved legacy source-record pages that remain readable
    but receive no current ingest writes.
  - `wiki/log.md`: optional human-readable operation log.
- `.knoarbor/` contains runtime and machine state:
  - `.knoarbor/facts/<source-key>/<revision-key>/`
  - `.knoarbor/index/`
  - `.knoarbor/ledgers/`
  - `.knoarbor/checkpoints/`
  - `.knoarbor/runs/`
  - `.knoarbor/queue/`
  - `.knoarbor/locks/`
  - `.knoarbor/logs/`
  - `.knoarbor/chat/sessions/`
- `maintenance/reports/<flow>/` stores user-readable Markdown reports.
- `maintenance/archives/` stores human-readable archived pages.
- The virtual `all` vault is not a physical directory.
- New writes use Vault Layout v2 paths; ingest projections write only to
  `wiki/pages/`.
- Readers and writers use Vault Layout v2 paths only.
- Every factual revision directory contains exactly `source.json`,
  `knowledge.json`, `diagnostics.json`, and `manifest.json`.
- Fact directory keys are deterministic filesystem-safe identities. Random
  names are limited to `.staging/` directories that are unreachable to readers.
- Fact JSON stores attachment references and hashes, not duplicate attachment
  binaries.
- Active fact selection is owned by the SQLite source head; directory ordering
  or modification time has no semantic meaning.

## Non-goals

- Moving the user's existing local vault content automatically.
- Rewriting historical report paths inside old Markdown reports.
- Making `maintenance/` part of the Obsidian-facing wiki.
- Preserving old typed page directories such as `` or ``.
- Exposing `.knoarbor/facts/**` as a normal user browsing surface.
- Keeping `source_revisions/generations/**` as a compatibility reader after the
  factual-layout migration closes.
