# Vault Layout v2 Design

## Standard Layout

```text
vaults/<id>/
  raw/
    inbox/
      documents/
      media/
      notes/
    normalized/
      chats/
      excerpts/
      markdown/
    assets/
      images/
      media/
      pages/
      tables/
    sidecars/
      documents/
      sources/
  wiki/
    pages/
    sources/
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
    queue/
    locks/
    logs/
    chat/
      sessions/
```

## Path Ownership

- `storage.vault_layout` is the single source of truth for physical vault paths.
- `storage.wiki_paths` maps logical wiki paths to the human-facing wiki layer.
- Logical page references keep their user-facing shape:
  - `Foo.md` resolves to `wiki/pages/Foo.md`.
  - `sources/Foo Source.md` resolves to `wiki/sources/Foo Source.md`.
- Report APIs return paths relative to the vault root, for example `maintenance/reports/ingest/ingest_report_<run_id>.md`.
- Ledger APIs return paths relative to the vault root, for example `.knoarbor/ledgers/ingest.jsonl`.

## Content Ownership

- `raw/inbox/**` stores user-provided input locations or copied input files.
- `raw/derived/markdown/**` stores source-faithful normalized text and Markdown.
- `raw/derived/assets/**` stores retained parsed assets such as images, media, page
  renders, and table assets.
- `raw/derived/metadata/**` stores parser and attachment metadata. The sidecar is the
  place for asset paths, hashes, MIME types, coordinates, OCR/VLM output, and
  parser-specific payloads.
- `wiki/pages/**` stores maintained knowledge pages using the frozen wiki page
  schema.
- `wiki/sources/**` stores source digest audit pages using the frozen source
  digest schema.
- `maintenance/**` stores human-readable reports and archives.
- `.knoarbor/**` stores machine runtime state, ledgers, indexes, queues, locks,
  and chat sessions.

## Compatibility

Vault Layout v2 is the only supported runtime layout. The resolver does not
read typed knowledge directories, root-level wiki pages, old report roots, or
old runtime ledgers. Tests and local experiments must create temporary vaults
with this layout instead of initializing or rewriting a user's configured
vault.

## Obsidian Guidance

Users who want to browse only maintained knowledge pages in Obsidian should
open `vaults/<id>/wiki/pages`. Users who want to inspect provenance can also
open `vaults/<id>/wiki`, where `sources/` contains source digest audit pages.
Opening the entire vault is supported for file inspection, but the intended
human knowledge surface is the `wiki` layer, while raw inputs, assets, reports,
and machine state remain outside normal wiki browsing.
