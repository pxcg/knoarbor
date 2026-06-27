# Vault Layout v2 Requirements

## Goal

KnoArbor vaults must separate human-readable wiki content from raw inputs, run reports, and machine runtime state. A user should be able to open the wiki layer in Obsidian without seeing ledgers, checkpoints, queues, locks, or maintenance artifacts.

## Requirements

- A vault root contains three visible top-level areas:
  - `raw/`: original or normalized input material.
  - `wiki/`: human-facing wiki publication layer.
  - `maintenance/`: human-readable operational reports and archives.
- `wiki/` contains only user-readable wiki material:
  - `wiki/pages/`: final knowledge pages.
  - `wiki/sources/`: source digest audit pages.
  - `wiki/log.md`: optional human-readable operation log.
- `.knoarbor/` contains runtime and machine state:
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
- New writes use Vault Layout v2 paths.
- Readers and writers use Vault Layout v2 paths only.

## Non-goals

- Moving the user's existing local vault content automatically.
- Rewriting historical report paths inside old Markdown reports.
- Making `maintenance/` part of the Obsidian-facing wiki.
- Preserving old typed page directories such as `` or ``.
