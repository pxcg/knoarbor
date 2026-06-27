# Provenance Design

This document defines KnoArbor's source provenance model. It keeps raw sources, source digests, knowledge pages, lint maintenance, and query context aligned under one shared meaning of "source".

```text
raw source -> source digest -> wiki page -> query context
```

## Goals

- Keep raw sources as immutable evidence.
- Make every generated page traceable to one or more sources.
- Use source digest pages as human-readable bridges between raw files and maintained knowledge pages.
- Use structured page-body evidence as the canonical source provenance model for single-source and multi-source pages.
- Let lint verify provenance chains with structured evidence rather than natural-language guessing.

## Source Layers

| Layer | Location / Field | Responsibility |
| --- | --- | --- |
| Raw Source | `raw/**` | Original input. It should not be rewritten by LLM workflows. |
| Source Digest | `wiki/sources/*.md` | Source-level audit page connecting one raw source to generated knowledge pages. |
| Knowledge Page | `wiki/pages/<slug>.md` | Reusable maintained knowledge page. Claims, relations, entities, synthesis, and evidence live in the page body and graph index. |

## Page-Body Source Evidence

Current pages keep source provenance in dedicated body sections. A knowledge page uses `## Evidence`; a source digest uses `## Source Identity`, `## Source Units`, `## Contribution Map`, and `## Raw Source`.

```markdown
## Evidence

| Claim | Source | Range | Basis | Confidence |
|---|---|---|---|---|
| C1 | raw/inbox/notes/Agent.md | unit:0 | The source describes Agent Loop control. | high |
```

Rules:

- `## Evidence` binds each claim to source, range, basis, and confidence. It is the knowledge page source-of-truth for raw source references.
- A knowledge page should have a matching source digest trace for each raw source it relies on.
- A source digest should record generated knowledge pages through its Contribution Map and machine index trace.
- One raw source should create at most one source digest in a single ingest batch. When long documents or chats are segmented, duplicate source digest drafts must be merged before writing.
- Ingest does not write broad navigation links into page bodies. Topical similarity and weak candidate matches remain retrieval/index signals, not persisted navigation sections.

## Multi-Source Model

Multi-source pages use multiple rows in `## Evidence`:

```markdown
## Evidence

| Claim | Source | Range | Basis | Confidence |
|---|---|---|---|---|
| C1 | raw/inbox/notes/Agent.md | unit:0 | Agent Loop control cycle. | high |
| C2 | raw/normalized/chats/session_20260505_173432_47d596.json | turn:4-6 | Production memory discussion. | medium |
```

Retrieval, lint, and relation logic read `## Evidence` and source digest trace sections as the source of truth.

## Lint Boundary

Lint may:

- check whether source references are complete across `## Evidence` and source digest trace sections;
- check whether raw sources exist;
- check whether source digests exist;
- check whether source digest traces and Contribution Maps are consistent with generated pages;
- create maintenance candidates for missing source digests and missing trace records.

Lint must not:

- guess provenance without structured Evidence, Source Identity, Raw Source, or Contribution Map evidence;
- verify facts through the network;
- treat normal wiki links as provenance sources;
- merge multiple sources automatically unless the operation explicitly updates structured Evidence rows and passes review.

## Migration Strategy

1. Keep source provenance in page-body evidence sections.
2. Validate source references from Evidence, Source Identity, Raw Source, and Contribution Map.
3. Keep frontmatter limited to page identity metadata such as creation time, update time, and content hash.
4. Verify that automatic provenance repair updates structured Evidence and source digest traces without mutating page identity metadata.

## Future Work

- Teach scanner to validate source completeness across Evidence, Source Identity, Raw Source, and Contribution Map.
- Support multi-source digest relationships.
- Expose source confidence and evidence ranges in query context packs.
