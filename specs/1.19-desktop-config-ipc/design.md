# Desktop Config IPC

## Problem

In the desktop app, settings edits are local configuration changes, but the renderer currently persists them through browser `fetch` calls to the local HTTP service. Enterprise DLP software can classify those requests as network uploads because the payload contains `config` data, even when the destination is `127.0.0.1` and the request uses JSON rather than multipart form data.

## Goals

- Move desktop configuration writes off browser HTTP and into Electron IPC.
- Keep read-only settings queries on the local runtime fast path so opening Settings does not spawn a Python helper for every panel.
- Keep renderer/browser mode on the existing HTTP API.
- Reuse the Python `UiConfigService` implementation so YAML rendering, validation, vault initialization, diagnostics, and summaries stay single-sourced.
- Keep workflow, chat, query, ingest, lint, model discovery, and page content operations on the local HTTP API.

## Non-Goals

- Replacing the local FastAPI service.
- Moving chat streaming or workflow execution into Electron main.
- Duplicating config schema or YAML rendering logic in TypeScript.
- Adding compatibility for removed legacy `.env` model-key structures.

## Design

The renderer detects `window.knoarborDesktop?.config`. The bridge name and IPC namespace follow the KnoArbor desktop branch so the company-project desktop build does not carry stale product naming. When present, config write functions call the desktop bridge:

- `saveConfig`
- `saveConfigForm`

Read-only settings functions use the local runtime API through the Electron renderer protocol. In packaged desktop builds this is a local `GET` path through Electron main, not a browser upload. When the bridge is absent, write functions keep using the existing HTTP API for browser/developer mode.

Electron main exposes these operations through IPC and invokes a local Python CLI command, `knoar desktop-config`, with JSON over stdin/stdout. The CLI delegates to `UiConfigService`, producing the same response shapes as the HTTP routes.

This keeps the desktop write path local and DLP-safe:

```text
renderer settings state
  -> Electron preload bridge
  -> Electron main IPC
  -> local Python CLI process
  -> UiConfigService
  -> config.yaml
```

The HTTP write path remains available only for browser mode and API users:

```text
browser settings state
  -> fetch PUT /config/form
  -> FastAPI
  -> UiConfigService
  -> config.yaml
```

Packaged desktop builds must not use this HTTP path for settings persistence.

## Atomic Config Persistence

`UiConfigService` is the only config-write authority for raw and structured
writes. It validates the complete candidate, writes a private temporary file in
the config directory, flushes it to durable storage, and atomically replaces
`config.yaml`. Electron bootstrap uses the same private-file expectations when
creating the initial config. Neither renderer nor Electron main performs
partial YAML edits.

## Vault Profile Removal

Vault profile removal is a configuration operation owned by `UiConfigService`.
The renderer persists the remaining profiles through the same config IPC path;
Electron exposes no arbitrary directory-deletion bridge for this interaction.
Deleting vault content is a separate, currently unsupported lifecycle and must
not be inferred from removing a profile.

## IPC Commands

- `knoarbor-desktop:config-read-raw`
- `knoarbor-desktop:config-write-raw`
- `knoarbor-desktop:config-read-form`
- `knoarbor-desktop:config-write-form`
- `knoarbor-desktop:config-diagnostics`
- `knoarbor-desktop:vaults`

## Validation

- Python unit tests cover the `desktop-config` CLI command without starting the HTTP server.
- Web build verifies the renderer type surface and desktop bridge fallback.
- Desktop build verifies preload/main IPC type compatibility.
