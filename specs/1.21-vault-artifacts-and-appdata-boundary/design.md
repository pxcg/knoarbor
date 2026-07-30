# Vault Artifacts And AppData Boundary Design

## Product Data Root

The installed desktop app uses one product-owned app data root. This keeps the
product easy to locate and avoids scattering default runtime data across user
directories.

```text
<local-app-data>/KnoArbor/
  config.yaml
  logs/
    desktop.log
    service.log
  state/
    endpoint.json
    service.json
    electron/
  cache/
    electron/
  tmp/
  vaults/
    default/
```

The default vault remains under `<app-data>/KnoArbor/vaults/default` until the
product explicitly introduces a user-facing vault location picker or migration
flow. External vault profiles can still point elsewhere, but the default install
does not create additional top-level product folders.

Platform roots are:

- macOS: `~/Library/Application Support/KnoArbor`;
- Windows: `%LOCALAPPDATA%/KnoArbor`;
- Linux: `${XDG_DATA_HOME:-~/.local/share}/KnoArbor`.

Electron `userData` and persistent `sessionData` are `state/electron`.
Root-aware backup filtering removes only its known rebuildable cache subtrees;
`cache/` remains reserved for app-owned disposable data. The product root is
resolved independently and remains the
authority for `config.yaml`, `vaults`, logs, and service state.

The local service writes exactly one endpoint record at
`state/endpoint.json`. A top-level `.knoarbor` and `~/.knoarbor` are not part of
the desktop contract.

## Vault Layout

```text
<vault>/
  raw/
    inbox/
      documents/
      notes/
      chats/
      media/
    derived/
      markdown/
      excerpts/
      assets/
        images/
        media/
        pages/
        tables/
      metadata/
        documents/
        sources/
  wiki/
    pages/
    sources/
    log.md
  artifacts/
    chat/
      <session-id>/
        images/
        files/
        manifest.json
  maintenance/
    reports/
      ingest/
      lint/
      query/
      run-failure/
    archives/
  .knoarbor/
    index/
    ledgers/
    checkpoints/
    runs/
    memory/
    chat/
      sessions/
    queue/
    locks/
    logs/
    tmp/
```

## Ownership

- `raw/inbox/**`: user-provided or copied source inputs.
- `raw/derived/markdown/**`: normalized source-faithful text from processors.
- `raw/derived/assets/**`: retained assets extracted from source inputs.
- `raw/derived/metadata/**`: parser output, attachment sidecars, hashes,
  coordinates, OCR/VLM descriptions, and source-specific metadata.
- `wiki/**`: human knowledge surface.
- `artifacts/**`: user-visible workflow outputs that are not source evidence by
  default.
- `maintenance/**`: user-readable workflow reports and archives.
- `.knoarbor/**`: machine runtime state. Indexes, checkpoints, queues, locks,
  ledgers, chat session records, memory records, and logs live here.

## Image Storage

Source attachments:

```text
raw/derived/assets/images/<source-id>/<sha20>.<ext>
raw/derived/metadata/sources/<source-id>.attachments.json
```

Chat generated images:

```text
artifacts/chat/<session-id>/images/<created-at>-<prompt-slug>-<sha20>.<ext>
artifacts/chat/<session-id>/manifest.json
```

The generated image manifest records provider, model, prompt, revised prompt,
MIME type, size, SHA-256 digest, created timestamp, session id, and generated
file path. Each item also records the Chat request identity that owns it so
turn replacement and deletion can reconcile the same durable artifact set.
Provider response URLs are transport-only inputs: after the bytes are retained,
the URL is discarded and is absent from the manifest and Chat tool trace.
Generated artifacts become knowledge evidence only through an
explicit import/adopt action that creates a source input or source record.

Chat session deletion removes the complete session artifact directory. Turn
deletion and successful regeneration remove only manifest entries and files
owned by the replaced request. Artifact reconciliation is performed by the Chat
session store, the same owner that commits the session lifecycle transition.

## Rendering Contract

UI-facing Markdown never uses absolute local filesystem paths. It may use:

- data URLs for transient external responses that could not be stored;
- vault-relative asset paths in persisted records;
- `/vault-assets/<encoded-path>?vault_path=<encoded-vault>` for rendered UI.

The asset route should allow only approved durable vault asset roots:

- `raw/derived/assets/**`
- `artifacts/**`

It should reject `.knoarbor/**`, `raw/inbox/**`, config files, and path
traversal attempts.

Generated-image Chat answers do not use the transient-data exception: image
generation succeeds only after the returned bytes have been retained below the
canonical artifact root.

## Global Chat Boundary

The virtual `all` vault is not a physical vault. Global/all-vault chat sessions
must not be represented as nested pseudo-vaults such as
`.knoarbor/global_chat/.knoarbor/chat/sessions`. The design options are:

- product-scoped global chat under `<app-data>/KnoArbor/state/chat/sessions/`;
- an explicit hidden system vault profile under `vaults/_system/`.

The preferred direction is product-scoped global chat because it is application
state, not a user knowledge vault. Vault-scoped chat remains under
`<vault>/.knoarbor/chat/sessions`.

Implementation note: chat session resolution uses an explicit session target.
Single-vault chat targets `<vault>/.knoarbor/chat/sessions` and
`<vault>/artifacts/chat`; all-vault chat targets
`<config-dir>/state/chat/sessions`, `<config-dir>/state/artifacts/chat`, and
`<config-dir>/state/ledgers/token.jsonl`. These paths must not create
`.knoarbor/global_chat` or `state/.knoarbor/chat/sessions`.

## Backup Contract

Durable vault backup:

- `wiki/**`
- `raw/inbox/**`
- `raw/derived/markdown/**`
- `raw/derived/assets/**`
- `raw/derived/metadata/**`
- `artifacts/**`
- `maintenance/reports/**`
- `maintenance/archives/**`

Optional continuity backup:

- `.knoarbor/chat/sessions/**`
- `.knoarbor/memory/**`
- `.knoarbor/ledgers/**`
- `.knoarbor/runs/**`
- `.knoarbor/checkpoints/**`

Rebuildable or disposable:

- `.knoarbor/index/**`
- `.knoarbor/locks/**`
- `.knoarbor/queue/**`
- `.knoarbor/tmp/**`
- `.knoarbor/logs/**`
- app data `cache/**`
- app data `tmp/**`
- app data `state/**`

`config.yaml` is durable but sensitive. It is backed up separately from the
vault content contract.

The desktop lifecycle helper selects `config.yaml`, durable product state, and
configured internal vaults explicitly. Disposable exclusions are evaluated
only at canonical app-owned relative roots. A user source directory named
`Cache`, `logs`, or `tmp` remains ordinary durable vault content.

## Portable Path Contract

Generated filenames use a bounded readable stem plus a stable digest. Each
generated segment is stripped of trailing dots/spaces and Windows-reserved
device names. Source attachment display names remain metadata and do not need
to be reproduced in full in the physical filename.

## Rejected Alternatives

- Move the default vault to `~/KnoArbor/Vaults/default`: rejected for now because
  the product should not scatter installed data across multiple directories.
- Keep generated images in `raw/derived/assets/images/generated/chat`: rejected
  because chat artifacts are not derived from raw source inputs.
- Store generated images under `.knoarbor/chat`: rejected because images are
  user-visible artifacts, not opaque machine runtime state.
- Serve arbitrary vault-relative paths through `/vault-assets`: rejected because
  it would expose raw inputs and runtime files beyond the intended rendering
  contract.
