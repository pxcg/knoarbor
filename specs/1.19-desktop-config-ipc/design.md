# Desktop Config IPC

## Problem

In the desktop app, settings edits are local configuration changes, but the renderer currently persists them through browser `fetch` calls to the local HTTP service. Enterprise DLP software can classify those requests as network uploads because the payload contains `config` data, even when the destination is `127.0.0.1` and the request uses JSON rather than multipart form data.

## Goals

- Move desktop configuration reads and writes off browser HTTP and into Electron IPC.
- Keep renderer/browser mode on the existing HTTP API.
- Reuse the Python `UiConfigService` implementation so YAML rendering, validation, vault initialization, diagnostics, and summaries stay single-sourced.
- Keep workflow, chat, query, ingest, lint, model discovery, and page content operations on the local HTTP API.

## Non-Goals

- Replacing the local FastAPI service.
- Moving chat streaming or workflow execution into Electron main.
- Duplicating config schema or YAML rendering logic in TypeScript.
- Adding compatibility for removed legacy `.env` model-key structures.

## Design

The renderer detects `window.knoarborDesktop?.config`. When present, config-related client functions call the desktop bridge:

- `getConfig`
- `saveConfig`
- `getConfigForm`
- `saveConfigForm`
- `getConfigDiagnostics`
- `getVaults`

When the bridge is absent, those functions keep using the existing HTTP API.

Electron main exposes these operations through IPC and invokes a local Python CLI command, `knoar desktop-config`, with JSON over stdin/stdout. The CLI delegates to `UiConfigService`, producing the same response shapes as the HTTP routes.

This keeps the desktop write path local:

```text
renderer settings state
  -> Electron preload bridge
  -> Electron main IPC
  -> local Python CLI process
  -> UiConfigService
  -> config.yaml
```

The HTTP write path remains available for browser mode and API users:

```text
browser settings state
  -> fetch PUT /config/form
  -> FastAPI
  -> UiConfigService
  -> config.yaml
```

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
