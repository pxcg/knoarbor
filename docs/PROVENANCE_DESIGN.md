# Provenance Design

This document explains KnoArbor's source provenance model. The frozen field and
directory contracts live in [Contracts](CONTRACTS.md); this page describes why
raw sources, source digests, knowledge pages, lint maintenance, and query
context share one meaning of "source".

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

Responsibilities:

- `## Evidence` binds each claim to source, range, basis, and confidence. It is
  the knowledge page source of truth for raw source references.
- A knowledge page has a matching source digest trace for each raw source it
  relies on.
- A source digest records generated knowledge pages through its Contribution Map
  and machine index trace.
- One raw source creates at most one source digest in a single ingest batch.
  Long documents or chats can be segmented; duplicate source digest drafts are
  merged before writing.
- Ingest keeps broad navigation links out of page bodies. Topical similarity and
  weak candidate matches remain retrieval/index signals.

## Multi-Source Model

Multi-source pages use multiple rows in `## Evidence`:

```markdown
## Evidence

| Claim | Source | Range | Basis | Confidence |
|---|---|---|---|---|
| C1 | raw/inbox/notes/Agent.md | unit:0 | Agent Loop control cycle. | high |
| C2 | raw/inbox/chats/session_20260505_173432_47d596.json | turn:4-6 | Production memory discussion. | medium |
```

Retrieval, lint, and relation logic read `## Evidence` and source digest trace sections as the source of truth.

## Lint Boundary

Lint owns:

- checking whether source references are complete across `## Evidence` and
  source digest trace sections;
- checking whether raw sources exist;
- checking whether source digests exist;
- checking whether source digest traces and Contribution Maps are consistent
  with generated pages;
- creating maintenance candidates for missing source digests and missing trace
  records.

Out of scope for lint:

- provenance guesses without structured Evidence, Source Identity, Raw Source,
  or Contribution Map evidence;
- network fact verification;
- normal wiki links as provenance sources;
- automatic multi-source merges outside operations that update structured
  Evidence rows and pass review.

## Migration Strategy

1. Keep source provenance in page-body evidence sections.
2. Validate source references from Evidence, Source Identity, Raw Source, and Contribution Map.
3. Keep frontmatter limited to page identity metadata such as creation time, update time, and content hash.
4. Verify that automatic provenance repair updates structured Evidence and source digest traces without mutating page identity metadata.

## Future Work

- Teach scanner to validate source completeness across Evidence, Source Identity, Raw Source, and Contribution Map.
- Support multi-source digest relationships.
- Expose source confidence and evidence ranges in query context packs.
