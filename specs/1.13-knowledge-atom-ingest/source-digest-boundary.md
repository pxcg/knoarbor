# Source Digest Boundary

## Purpose

This note freezes the design discussion about whether KnoArbor should keep
source pages after raw files and compiled wiki pages already exist.

The decision is:

> Keep source digest capability, but do not treat source digests as ordinary
> knowledge pages.

A source digest is a provenance and audit artifact. It records how one raw
source, or one source segment, contributed to the maintained wiki. It should
help users and maintainers inspect the raw-to-wiki compilation path without
competing with knowledge pages as the primary answer surface.

## First-Principles Question

The first-principles question is not whether a source page looks useful in a
traditional wiki. The question is:

> If raw sources and knowledge pages already exist, what unique question does a
> source digest answer?

The answer is:

> What did this raw source contribute to the maintained wiki?

Raw sources answer:

> What was the original material?

Knowledge pages answer:

> What is currently known about a stable subject?

Source digests answer:

> How was this source interpreted, extracted, accepted, rejected, and linked
> into the wiki?

## Boundary

### Raw Source

Raw sources are immutable or source-faithful inputs:

- Markdown notes;
- chat records;
- PDFs or parsed documents;
- web captures;
- connector outputs.

Raw sources preserve the original material. They are not optimized for reading,
query answering, maintenance, or page-level reasoning.

### Cardinality Model

The normal compilation relationship is:

```text
raw source or raw segment
  -> source digest
    -> one or more knowledge pages
```

More precisely:

- one raw source can be split into multiple source segments;
- each raw source or source segment can produce one source digest;
- one source digest can contribute claims, entities, relations, or evidence to
  multiple knowledge pages;
- one knowledge page can be maintained by multiple source digests across time.

Example:

```text
raw/inbox/notes/Agent.md
  -> sources/Agent-Source-Digest.md
    -> Agent Loop.md
    -> Tool Calling.md
    -> Session Memory.md
    -> Multi-Agent Orchestration.md
```

For a long PDF or long chat record:

```text
raw/inbox/documents/AgentBook.pdf
  -> segment: Agent Loop
      -> sources/AgentBook-Agent-Loop-Digest.md
  -> segment: Memory
      -> sources/AgentBook-Memory-Digest.md
  -> segment: Tool Calling
      -> sources/AgentBook-Tool-Calling-Digest.md
```

Knowledge pages then accumulate source-level contributions:

```text
Agent Loop.md
  <- sources/Agent-Source-Digest.md
  <- sources/OpenClaw-Architecture-Digest.md
  <- sources/Claude-Code-Agent-Loop-Digest.md
```

This relationship is why source digests remain useful even after knowledge
pages exist. They are the compilation record between raw material and one or
more maintained knowledge pages.

### Knowledge Page

Knowledge pages are subject-oriented wiki projections. They maintain a stable
knowledge object through claims, entities, relations, evidence, synthesis, and
source references.

They answer questions like:

- What is Agent Loop?
- What claims are maintained about this topic?
- Which entities are involved?
- Which relations connect this topic to other pages?
- Which sources support these claims?

### Source Digest

Source digests are source-oriented audit views. They describe how one source
contributed to the wiki.

They answer questions like:

- What is this source?
- What does it mainly discuss?
- Which claims, entities, and relations were extracted?
- Which wiki pages were created or updated?
- Which material was rejected or left unresolved?
- How can a user return to the raw material?

## Why Source Digests Should Remain

### Compilation Trace

Raw files show the original material, but they do not explain how ingest used
that material. Knowledge pages show the maintained result, but they do not
always show the source-level compilation decision.

A source digest records the intermediate trace:

```text
raw source
  -> normalized source units
  -> evidence-backed atoms
  -> generated or updated pages
  -> rejected or unresolved material
```

This is important for debugging, review, and explaining why an ingest run
produced a given page.

### Incremental Maintenance

When a raw source changes or is re-ingested, the system needs to know what that
source previously contributed. Source digests make it easier to compare prior
and current contributions without rereading the full raw file or reverse
engineering every knowledge page.

### Quality Audit

When a claim looks suspicious, maintainers need a trace:

```text
claim
  -> evidence
  -> source digest
  -> raw source
```

The source digest explains how the source was understood during ingest. Raw
alone can verify the material, but not the model's extraction and allocation
decisions.

### Source-Level Queries

Some user questions are source-oriented:

- What did this chat session contribute?
- What did this PDF mainly say?
- Which pages did this note update?
- Which extracted items were rejected?

These questions should be answered by source digests, not by ordinary knowledge
pages.

## Why Source Digests Should Be Demoted

Source digests should not be treated as normal knowledge pages because they are
organized by source, not by subject. If they compete with knowledge pages in
normal query or browsing, users may be unsure whether to read the source digest
or the maintained subject page.

Default behavior:

- query/chat should prefer knowledge pages for subject questions;
- source digests should serve provenance, audit, and source-intent questions;
- frontends may show source digests through a provenance or source view, not as
  equal neighbors in the main knowledge page list.

## Recommended Source Digest Shape

```md
# Agent Loop Source Digest

## Source Identity

- Source: raw/inbox/notes/Agent.md
- Connector: markdown
- Content hash: ...
- Ingest run: ...

## Audit Summary

This audit record covers one Markdown source, 2 stable source units, 2 accepted
contributions, 0 rejected contributions, and one raw source pointer.

## Source Units

| Unit | Source | Range | Basis | Confidence |
|---|---|---|---|---|
| U1 | raw/inbox/notes/Agent.md | section:Agent Loop | source introduces the loop cycle | high |
| U2 | raw/inbox/notes/Agent.md | section:Production | source describes production modules | medium |

## Contribution Map

| Item | Contribution | Evidence Units | Target Page |
|---|---|---|---|
| C1 | Agent Loop advances tasks through repeated reasoning, action, observation, and state update. | U1 | pages/Agent-Loop.md |
| C2 | Production Agent Loops require tool calling, context management, and observability. | U2 | pages/Agent-Infrastructure.md |

## Unresolved / Rejected

- Some OpenClaw implementation details were left unresolved because the source
  did not provide enough direct evidence.

## Attachments

| Attachment | Type | Topic | Description | Source Range | Status |
|---|---|---|---|---|---|
| A1 | image | Agent Loop flowchart | Diagram showing a user task entering an agent loop, tool calls, and memory feedback. | page_idx:0 | candidate |

## Raw Source

- raw/inbox/notes/Agent.md
```

## Attachment Boundary

Attachments are provenance material attached to a source digest. They are not
ordinary knowledge claims and should not expand the source digest into a parser
log.

Readable source digest pages keep only:

- `attachment`: stable local attachment id such as `A1`;
- `type`: image, table, file, or other;
- `topic`: what the attachment is about;
- `description`: a short human-readable summary;
- `source_range`: page, region, table block, OCR block, or source-unit pointer;
- `status`: candidate, used, or skipped.

Attachment sidecars keep the audit details:

- retained asset path;
- page index;
- bounding box or source region;
- MIME type;
- content hash;
- MinerU/VLM/OCR raw extraction content;
- extracted image structure, table structure, or model output.

For images parsed by MinerU VLM or hybrid backends, the raw image file is kept
under `raw/assets/**`, while the VLM/OCR extraction is stored in
`raw/sidecars/**`. The semantic ingest pipeline may read the attachment
metadata to understand the source. Image-backed claims are represented through
normal evidence rows that point to the source digest, source range, and basis.

## Ingest Design Implications

- Source digests are produced by the source digest layer, before knowledge atom
  extraction and page drafting.
- Source digests can be written as Markdown views, but they remain provenance
  artifacts rather than primary knowledge objects.
- Source digest Markdown should use source identity, audit summary, source
  units, contribution map, unresolved/rejected material, and raw source
  pointers. The audit summary is generated from processing facts rather than
  semantic source prose. It should not use the ordinary knowledge-page
  `Claims`/`Entities`/`Relations`/`Evidence`/`Synthesis` section set.
- Attachment rendering must be compact. Full parser output belongs to sidecar
  metadata and frontend/debug surfaces, not the default Markdown body.
- Knowledge pages may reference source digests in their `Sources` or evidence
  mappings.
- Reports should show which source digests contributed to written pages.
- Query and chat should select source digests only when the user intent is
  source, provenance, audit, raw-material inspection, or evidence inspection.

## Rejected Alternatives

- Delete source digests and rely only on raw files plus knowledge pages. This
  loses source-level compilation trace and makes ingest debugging harder.
- Treat source digests as ordinary knowledge pages. This confuses source
  provenance with maintained subject knowledge.
- Copy full raw content into source digests. This recreates chunk-like RAG
  material and bloats the wiki.
- Use source digests as the primary answer surface for subject questions.
  Subject questions should be answered by maintained knowledge pages.

## Frozen Principle

> Source digest is not a knowledge page. It is the compiled provenance record of
> one raw source or source segment.

The maintained wiki is therefore layered:

```text
raw/             original material
source digest    source-level compilation trace
knowledge pages  subject-level maintained wiki
atom/index       machine-readable claims, entities, relations, evidence
```
