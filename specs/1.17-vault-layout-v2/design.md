# Vault Layout v2 Design

## Standard Layout

```text
vaults/<id>/
  raw/
    inbox/
      documents/
      chats/
      media/
      notes/
    derived/
      excerpts/
      markdown/
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
  maintenance/
    reports/
      ingest/
      lint/
      query/
      run-failure/
    archives/
  .knoarbor/
    facts/
      .staging/
      <source-key>/
        <revision-key>/
          source.json
          knowledge.json
          diagnostics.json
          manifest.json
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
  - legacy `sources/Foo Source.md` resolves to `wiki/sources/Foo Source.md`.
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
- `wiki/sources/**` is a reserved readable namespace for legacy source record
  audit pages. Current ingest does not write it.
- `maintenance/**` stores human-readable reports and archives.
- `.knoarbor/**` stores machine runtime state, ledgers, indexes, queues, locks,
  and chat sessions.
- `.knoarbor/facts/**` stores immutable source revisions. `source.json` owns
  normalized source identity, units, ranges, and attachment metadata;
  `knowledge.json` owns accepted synthesis, entities, claims, relations, and
  evidence; `diagnostics.json` owns non-factual extraction audit data;
  `manifest.json` binds the revision identity and file hashes.
- `<source-key>` and `<revision-key>` are deterministic safe encodings or hashes
  of typed identities. They are path identities rather than display labels.
- `.knoarbor/facts/.staging/<random>/` is the only random fact path. Readers
  never inspect staging, and successful publication atomically renames a staged
  tree to its deterministic revision path.

## Compatibility

Vault Layout v2 is the only supported runtime layout. The resolver does not
read typed knowledge directories, root-level wiki pages, old report roots, or
old runtime ledgers. Tests and local experiments must create temporary vaults
with this layout instead of initializing or rewriting a user's configured
vault.

The implemented fact amendment migrates active
`.knoarbor/source_revisions/generations/**` content during the bounded 1.37
startup migration. After verification, production readers and writers use only
`.knoarbor/facts/**`; the legacy tree is removed rather than retained as a
fallback authority.

## Obsidian Guidance

Users who want to browse maintained projections in Obsidian should open
`vaults/<id>/wiki/pages`. Existing `wiki/sources/` content is historical;
current provenance is inspected through structured facts, raw units, reports,
and projection metadata.
Opening the entire vault is supported for file inspection, but the intended
human knowledge surface is the `wiki` layer, while raw inputs, assets, reports,
and machine state remain outside normal wiki browsing.
