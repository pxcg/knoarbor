# Core Concepts

KnoArbor is an AI-native knowledge engine that compiles multi-source information into a traceable, maintainable local knowledge network. Its factual authority is the immutable source and knowledge revision store selected by active SQLite heads; Markdown wiki pages and machine indexes are rebuildable projections for people and tools.

## Raw Source

Raw sources are original inputs:

- AI chat sessions.
- Markdown notes.
- Parsed rich-document Markdown outputs, such as documents converted by MinerU.
- Web captures.
- Transcripts.

Raw sources are preserved for provenance. Automated workflows should not rewrite them.

## SourceDocument

`SourceDocument` is the normalized source contract used by ingest. Connectors convert different source types into this shared shape before semantic workflows run.

This keeps the rest of the system independent from source-specific details.

## Vault Authorities And Projections

The maintained wiki uses one canonical layout per vault:

- `wiki/pages/<slug>.md`: maintained knowledge pages.
- `.knoarbor/facts/`: immutable source processing and knowledge
  generations selected by SQLite active heads. Older vaults may also contain
  legacy `wiki/sources/*.md` audit pages.
- `raw/**`: original or normalized source material.
- `maintenance/reports/**`: human-readable run reports.
- `.knoarbor/index/**`: machine indexes for page lookup and graph traversal.

Knowledge pages do not use physical type directories. Their maintained structure
lives in page sections: `Summary`, `Claims`, `Relations`, `Synthesis`,
`Entities`, and `Evidence`. UI browsing views are derived from
`.knoarbor/index/graph_index.json` rather than written as wiki files.

## Ingest

Ingest commits new source material as immutable factual revisions and then
materializes wiki and index projections:

```text
Connector / Document Processor
  -> SourceDocument
  -> Freeze / Normalize / Segment
  -> Source Units
  -> Knowledge Atoms + Evidence Edges
  -> Atomic Revision Publication
  -> Wiki / Index Materialization
  -> Report
```

Connectors and document processors only prepare source material. Semantic ingest
owns factual extraction and evidence linkage; materialization derives readable
pages and navigation indexes from the committed revision. Projection failure is
recovered by rematerializing the active revision without repeating model work.
Merge, archive, delete, rename, and long-term page lifecycle governance belong
to lint/maintenance.

## Lint

Lint keeps the wiki maintainable:

```text
Scan -> Diagnose -> Review -> Policy -> Apply -> Rescan -> Report
```

Deterministic lint checks structure, links, source provenance, and page contracts. Semantic lint reviews quality, boundary, duplication, and maintainability.

## Query

Query retrieves claim-backed raw evidence for Chat or a host AI tool:

```text
User query -> Rank active atoms -> Select claims -> Resolve active raw units
           -> Evidence pack -> Chat / host AI answer
```

Query is deterministic and model-free. Pages may provide navigation locators,
but only complete raw units reached through explicit claim evidence edges supply
factual answer material. KnoArbor does not need to replace Hermes, Codex,
OpenClaw, Claude Code, or other assistants; it provides durable context and
provenance.

## Runtime Vaults

The `vaults/` directory contains local runtime vaults, not source code. It is
ignored by git by default. A default install uses `vaults/default/`; additional
knowledge bases can live beside it, such as `vaults/work/` or
`vaults/personal-study/`.
