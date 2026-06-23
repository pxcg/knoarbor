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

The maintained wiki is stored under `pages/`. Source digest pages stay in
`pages/sources/`; ordinary knowledge pages use the flat `pages/<slug>.md`
namespace.

Page type is described by metadata rather than by mandatory physical
directories:

- `page_kind`: concept, entity, workflow, comparison, timeline, query, note, or
  source digest.
- `role`: knowledge page, source digest, generated view, or report.
- `facets`: searchable and browsable labels such as `agent_architecture`,
  `workflow_pattern`, `claims`, or `relations`.
- `canonical_path`: the current stable path.
- `legacy_paths`: old paths that still resolve after migration.

Generated `_views/` pages and the console provide human browsing by concepts,
entities, workflows, comparisons, open questions, and source audit. Page
`Claims` and `Relations` sections carry evidence-backed statements and typed
edges; `.knoarbor/index/` stores the machine-readable index, atoms, run state,
and ledgers.

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
