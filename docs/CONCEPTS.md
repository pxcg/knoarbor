# Core Concepts

KnoArbor is an AI-native wiki engine that compiles multi-source information into a traceable, maintainable knowledge network. It is built around three phases and one durable artifact: a Markdown wiki vault.

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

## Wiki Page Identity

The maintained wiki uses one canonical layout per vault:

- `wiki/pages/<slug>.md`: maintained knowledge pages.
- `wiki/sources/<slug>.md`: source digest and audit pages.
- `raw/**`: original or normalized source material.
- `maintenance/reports/**`: human-readable run reports.
- `.knoarbor/index/**`: machine indexes for page lookup and graph traversal.

Knowledge pages do not use physical type directories. Their durable structure
lives in page sections: `Summary`, `Claims`, `Relations`, `Synthesis`,
`Entities`, and `Evidence`. UI browsing views are derived from
`.knoarbor/index/graph_index.json` rather than written as wiki files.

## Ingest

Ingest compiles new source material into wiki pages:

```text
Connector / Document Processor
  -> SourceDocument
  -> Checkpoint / Segmentation
  -> Source Normalize
  -> Source Digest
  -> Knowledge Atoms
  -> Page Plan
  -> Draft Compile / Review
  -> Write / Index / Report
```

Connectors and document processors only prepare source material. Semantic ingest
decides whether to create, update, or skip pages. It should not blindly create
one page per source. Merge, archive, delete, rename, and long-term page lifecycle
governance belong to lint/maintenance.

## Lint

Lint keeps the wiki maintainable:

```text
Scan -> Diagnose -> Review -> Policy -> Apply -> Rescan -> Report
```

Deterministic lint checks structure, links, source provenance, and page contracts. Semantic lint reviews quality, boundary, duplication, and maintainability.

## Query

Query retrieves wiki context for a host AI tool:

```text
User query -> Search wiki -> Context pack -> Host AI answer
```

KnoArbor does not need to replace Hermes, Codex, OpenClaw, Claude Code, or other assistants. It provides durable context and provenance.

## Runtime Vaults

The `vaults/` directory contains local runtime vaults, not source code. It is
ignored by git by default. A default install uses `vaults/default/`; additional
knowledge bases can live beside it, such as `vaults/work/` or
`vaults/personal-study/`.
