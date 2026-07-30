# Vault Layout v2 Tasks

## Status

Accepted baseline with the fact-layout amendment implemented.

- [x] Add a dedicated vault path helper layer.
- [x] Route current projections to `wiki/pages` and retain `wiki/sources` only
  as a readable legacy namespace.
- [x] Initialize new vaults with the standard layout.
- [x] Route Markdown reports to `maintenance/reports/<flow>`.
- [x] Route ledgers and checkpoints to `.knoarbor`.
- [x] Update tests and documentation references.
- [x] Verify report listing, page listing, ingest checkpoint, and token analysis on the new layout.

## Fact Layout Amendment

- [x] Add fact path helpers to `storage.vault_layout`.
- [x] Route factual staging to `.knoarbor/facts/.staging`.
- [x] Route published revisions to deterministic source/revision directories.
- [x] Enforce the four-file revision shape and relative attachment references.
- [x] Migrate legacy generations through the bounded 1.37 startup migration.
- [x] Delete legacy fact path readers and writers after migration verification.
- [x] Update backup, recovery, architecture, and provenance documentation.
