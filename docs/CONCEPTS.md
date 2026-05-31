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

## Wiki Page Types

The wiki is organized by page responsibility:

- `sources/`: source digest pages for raw inputs.
- `entities/`: named objects such as tools, products, organizations, people, or schools.
- `concepts/`: reusable methods, patterns, architectures, and principles.
- `comparisons/`: comparison-first artifacts.
- `queries/`: useful Q&A that is not yet stable enough to become another page type.
- `claims/`: atomic, evidence-backed claims.
- `timelines/`: chronology-first pages.
- `workflows/`: reusable procedures.
- `maintenance/`: reports and ledgers.

## Ingest

Ingest compiles new source material into wiki pages:

```text
SourceDocument -> KnowledgeExtract -> RelationPlan -> DraftBatch -> Review -> Write
```

Ingest decides whether to create, update, or skip pages. It should not blindly create one page per source. Merge, archive, delete, rename, and long-term page lifecycle governance belong to lint/maintenance.

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

## Runtime Vault

The `wiki/` directory is runtime data, not source code. It is ignored by git by default.
