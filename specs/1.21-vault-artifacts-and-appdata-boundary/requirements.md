# Vault Artifacts And AppData Boundary Requirements

## Goal

KnoArbor must make installed application data easy to understand, back up, and
clean without scattering default runtime data across multiple user directories.
The default desktop vault remains under the desktop app data root for now, but
the directories inside that root must have clear ownership.

## Requirements

- A fresh desktop install keeps user data under one product-owned app data root:
  - `config.yaml` for local product configuration.
  - `logs/` for desktop and managed service process logs.
  - `state/` for service endpoint and process state.
  - `cache/` and `tmp/` for disposable app runtime data.
  - `vaults/<vault-id>/` for user-owned knowledge vaults.
- The product-owned root is local, non-roaming application data: macOS
  `Application Support/KnoArbor`, Windows `%LOCALAPPDATA%/KnoArbor`, and Linux
  `${XDG_DATA_HOME:-~/.local/share}/KnoArbor`.
- The only desktop runtime endpoint is `state/endpoint.json`. No endpoint or
  other desktop runtime authority is written under a top-level `.knoarbor/` or
  the user's home directory.
- Electron profile, Local Storage, cookies, preferences, and persistent session
  data stay below `state/electron/`; backups exclude only its known rebuildable
  cache subtrees. App-owned disposable data stays below `cache/`.
- A vault separates source-derived knowledge assets from chat/tool artifacts:
  - `raw/derived/assets/**` is only for assets derived from input sources.
  - `artifacts/**` is for user-visible assets created by chat tools or other
    interactive workflows.
  - `.knoarbor/**` remains machine runtime state and must not contain large
    user-facing image assets.
- Source attachment images from MinerU, Markdown, or other source processors are
  retained as source-derived assets.
- Generated images from chat are retained as chat artifacts, not source-derived
  assets.
- Generated-image records retain only local durable asset identity and declared
  generation metadata; provider download URLs and their query credentials are
  never persisted.
- Deleting a Chat turn or session removes the generated artifacts owned only by
  that turn or session without affecting other turns or source-derived assets.
- Asset rendering uses a service-mediated route instead of absolute filesystem
  paths.
- Backup guidance distinguishes durable vault content, optional audit/runtime
  continuity, and disposable runtime/cache data.
- The physical `all` vault and global chat storage must have an explicit
  boundary; nested pseudo-vault runtime paths are not acceptable.
- New code writes only the canonical layout.
- Service logs are size-bounded and rotate within `logs/`.
- Backup selects durable product roots by their canonical relative paths and
  excludes disposable roots by exact app-owned location, never by matching an
  arbitrary user directory name.
- Generated filesystem path segments are bounded and portable across supported
  macOS and Windows filesystems.

## Non-Goals

- Moving the default desktop vault outside the app data root.
- Preserving old runtime layout compatibility.
- Migrating existing user vaults automatically.
- Treating generated chat images as source evidence automatically.
- Making application caches, Electron profile data, locks, queues, or temp files
  part of the durable backup contract.

## Acceptance Criteria

- A fresh desktop bootstrap creates no `raw/normalized`, `raw/assets`,
  `raw/sidecars`, or `raw/derived/assets/images/generated/chat` directories.
- A fresh desktop bootstrap creates no top-level `.knoarbor/`, and starting the
  service creates exactly one `state/endpoint.json`.
- A generated image is saved below `artifacts/chat/<session-id>/images/` and is
  renderable in chat.
- A generated image that cannot be retained locally fails the capability instead
  of persisting a remote provider URL.
- A document attachment image is saved below `raw/derived/assets/images/` and is
  renderable from wiki/chat evidence.
- App diagnostics expose app data, logs, state, config, and vault roots as
  distinct concepts.
- Docs and doctor-style checks state what should be backed up and what can be
  rebuilt or deleted.
- A backup/restore fixture preserves a user directory named `Cache`, `logs`, or
  `tmp` when it is part of durable vault content.
