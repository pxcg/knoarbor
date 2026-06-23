# Schema Boundary

## Purpose

This note freezes the design boundary for KnoArbor wiki schema.

The decision is:

> Schema is a system rule layer, not wiki knowledge content.

Schema defines how wiki pages, source digests, relations, evidence, and
machine-maintained structures should be generated, linted, queried, and
maintained. It should not be treated as a normal knowledge page.

## First-Principles Question

The first-principles question is:

> If raw sources, source digests, and knowledge pages already exist, why does
> the vault still need schema?

The answer is:

> Schema keeps LLM-maintained knowledge consistent over time.

Without schema, page generation can drift into free-form summaries, relation
names can fragment, evidence can become inconsistent, and lint cannot enforce a
stable contract.

## Boundary

### What Schema Answers

Schema answers:

- Which fields and sections should a knowledge page use?
- Which fields and sections should a source digest use?
- How should claims be numbered?
- How should entities be marked?
- How should relations be represented?
- How should evidence link claims to source ranges?
- Which relation predicates are accepted?
- Which constraints should ingest, lint, query, and chat share?

### What Schema Does Not Answer

Schema does not answer:

- What does the knowledge base know?
- Which pages should the user read first?
- Which raw source is authoritative?
- Which claim should win when sources conflict?
- Which pages are related for a particular user query?

Those are handled by pages, source digests, reports, indexes, and query/chat
selection.

## Storage Boundary

Schema should not live in `wiki/pages/`, because it is not user knowledge. It
should not be mixed into `wiki/sources/`, because it is not source provenance.
It should not be mixed into `wiki/raw/`, because it is not raw input material.

Recommended vault layout:

```text
vault/
  wiki/
    raw/
    sources/
    pages/
  .knoarbor/
    schema/
    index/
    reports/
```

`wiki/` remains the user-facing knowledge surface. `.knoarbor/schema/` contains
rules used by the system and maintainers.

Project-level built-in schema can also live in the application source tree, but
vault-level schema overrides or snapshots should live under `.knoarbor/schema/`
when needed.

## Schema Families

### Wiki Page Schema

The wiki page schema defines the maintained knowledge page shape.

Current frozen page elements:

- `Identity`
- `Summary`
- `Claims`
- `Entities`
- `Relations`
- `Evidence`
- `Synthesis`

Minimal identity fields:

- `created`
- `updated`
- `content_hash`

Knowledge page rules:

- Claims are the main content layer.
- Claims must use stable claim numbers such as `C1`, `C2`, and `C3`.
- Claims should mark entities with wiki links, such as `[[Agent Loop]]`.
- Entities are the knowledge objects mentioned by claims.
- Relations are claim-backed triples between entities.
- Relations should use a tabular triple form:

  ```md
  | Subject | Predicate | Object | Based on |
  |---|---|---|---|
  | [[Agent Loop]] | contrasts_with | [[Workflow]] | C2 |
  ```

- Evidence must map to claim numbers.
- Evidence must include `source`, `range`, `basis`, and `confidence`.
- Synthesis must be derived from claims, relations, and evidence. It must not
  introduce unsupported facts.

Example section order:

```md
## Summary

## Claims

## Entities

## Relations

## Evidence

## Synthesis
```

### Source Digest Schema

The source digest schema defines source-level audit documents.

Source digests are not ordinary knowledge pages. They record how one raw source
or raw segment contributed to the maintained wiki.

Recommended source digest sections:

- `Source Identity`
- `Source Summary`
- `Extracted Claims`
- `Mentioned Entities`
- `Generated Or Updated Pages`
- `Rejected Or Unresolved Material`
- `Raw Source`

Source digest rules:

- The digest is organized by source, not by subject.
- It should record extracted claims, mentioned entities, page impacts, rejected
  material, unresolved material, and raw source references.
- It should support audit and source-level query.
- It should not be selected as the primary answer object for ordinary subject
  questions.

### Evidence Schema

Evidence links a claim to source support.

Minimum evidence fields:

- `source`
- `range`
- `basis`
- `confidence`

Field meanings:

- `source`: source digest or source reference used as evidence;
- `range`: source section, page, paragraph, turn range, segment, or other
  location hint;
- `basis`: short explanation of why the source range supports the claim;
- `confidence`: support strength, preferably `high`, `medium`, or `low`.

Evidence rules:

- Evidence answers "why can this claim be trusted?"
- Evidence is claim-level, not only page-level.
- Evidence is not the same as raw source text.
- Evidence should be specific enough to audit but compact enough to keep the
  page readable.

### Relation Vocabulary

Relations connect entities through claim-backed triples.

Recommended initial predicate vocabulary:

- `depends_on`
- `requires`
- `contrasts_with`
- `uses`
- `implements`
- `supports`
- `constrains`
- `part_of`
- `derived_from`
- `coordinates`
- `includes`
- `can_mask`
- `preferred_over`

Relation rules:

- Relations must have `Subject`, `Predicate`, `Object`, and `Based on`.
- `Based on` must reference one or more claim numbers.
- Relations should be extracted from claims, not invented from loose topical
  similarity.
- Wikilinks are navigation. Relations are typed semantic edges.
- Related pages are a query/navigation view derived from relations and indexes,
  not a default wiki page section.

## Index Boundary

KnoArbor does not require `wiki/index.md` by default. The machine index is a
graph-first index under `.knoarbor/index/`:

```text
.knoarbor/index/
  manifest.json
  graph_index.json
```

The detailed index boundary is frozen in
[Index Boundary](index-boundary.md).

If `index.md` is ever generated, it is an optional export view, not the source
of truth for schema, retrieval, page lists, or graph structure.

## Rejected Alternatives

- Store schema as normal knowledge pages under `wiki/pages/`. This confuses
  system rules with user knowledge.
- Store schema inside `wiki/sources/`. Schema is not provenance from raw input.
- Use `index.md` as a machine index or schema file. KnoArbor's default machine
  index is `manifest.json` plus `graph_index.json`.
- Let prompts define schema implicitly. Schema must be explicit so ingest,
  lint, query, chat, and tests share the same contract.
- Allow unrestricted relation predicates. This fragments the graph and makes
  query behavior unpredictable.

## Frozen Principle

> Schema is the contract that keeps LLM-maintained wiki pages consistent. It is
> used by ingest, lint, query, chat, reports, and tests, but it is not itself a
> knowledge page.
