# Provenance Design

This document defines KnoArbor's source provenance model. It keeps raw sources, source digests, knowledge pages, lint maintenance, and query context aligned under one shared meaning of "source".

```text
raw source -> source digest -> wiki page -> query context
```

## Goals

- Keep raw sources as immutable evidence.
- Make every generated page traceable to one or more sources.
- Use source digest pages as human-readable bridges between raw files and maintained knowledge pages.
- Support future multi-source pages without breaking the current single `source` field.
- Let lint verify provenance chains with structured evidence rather than natural-language guessing.

## Source Layers

| Layer | Location / Field | Responsibility |
| --- | --- | --- |
| Raw Source | `raw/**` | Original input. It should not be rewritten by LLM workflows. |
| Source Digest | `pages/sources/*.md` | Readable summary, source focus, key points, and backlinks to generated pages. |
| Knowledge Page | `pages/<slug>.md` | Reusable maintained knowledge objects. Page kind and facets live in metadata; claims and typed relations live inside pages and the machine atom index. |

Legacy typed knowledge directories such as `pages/concepts/` remain readable
during migration, but they are no longer the canonical type model.

## Current Compatible Field

Current pages keep a single primary source:

```yaml
source: raw/notes/Agent.md
```

Rules:

- `source` means primary source.
- The `## Source` section must match the frontmatter `source`.
- A single-source knowledge page should have a matching source digest.
- A source digest should link back to the knowledge pages generated from the same raw source.
- One raw source should create at most one source digest in a single ingest batch. When long documents or chats are segmented, duplicate source digest drafts must be merged before writing.
- Ingest-stage Related Pages should primarily express provenance. Broad topical similarity or weak candidate matches should not be automatically written as page links; lint and query can evaluate those relationships later.

## Target Multi-Source Model

Multi-source pages should use structured frontmatter rather than prose-only source notes:

```yaml
source: raw/notes/Agent.md
sources:
  - path: raw/notes/Agent.md
    role: primary
  - path: raw/chats/session_20260505_173432_47d596.json
    role: supporting
```

Roles:

- `primary`: the main source for the page.
- `supporting`: supplementary facts, examples, explanation, or context.
- `derived_from`: content migrated or compiled from another source digest or knowledge page.

The legacy `source` field remains a compatibility field and is equivalent to `sources[0].path`. New retrieval, lint, and relation logic should prefer `sources[]` once supported.

## Lint Boundary

Lint may:

- check whether `source` and `## Source` are synchronized;
- check whether raw sources exist;
- check whether source digests exist;
- check whether source digests and knowledge pages link to each other;
- create maintenance candidates for missing source digests, missing backlinks, and inconsistent source fields.

Lint must not:

- guess provenance without structured `source_file`, `source`, or `sources[]` evidence;
- verify facts through the network;
- treat normal related-page links as provenance sources;
- merge multiple sources automatically unless the operation explicitly carries structured `sources[]` parameters and passes review.

## Migration Strategy

1. Keep the current single-source path stable.
2. Identify multi-source needs in schemas, docs, and lint diagnostics.
3. Add `sources[]` support only in storage, retrieval, provenance, and reviewed operations.
4. Verify that frontmatter and `## Source` remain synchronized after any automatic provenance repair.

## Future Work

- Add optional `sources[]` to page schema.
- Teach scanner to validate `source` and `sources[]` consistency.
- Support multi-source digest relationships.
- Expose primary/supporting source roles in query context packs.
