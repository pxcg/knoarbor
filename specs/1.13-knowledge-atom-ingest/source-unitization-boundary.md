# Source Unitization Boundary

## Purpose

Source Unitization creates stable provenance units from a normalized source or
source segment. A source unit is the evidence and audit granularity used by
source digests, knowledge atoms, reports, and later page citations.

This boundary is separate from Source Segmentation:

- a segment is an execution and budget window;
- a source unit is a provenance and evidence span;
- a short source can remain one segment while still producing several source
  units;
- a long source can produce many segments, each with its own local source units
  that are remapped during source-level aggregation.

## Ownership

Owner: source pipeline and deterministic parsing helpers.

Inputs:

- `SourceDocument` after source input and checkpoint window selection;
- `SourceSegment` when a source has been segmented for budget;
- connector metadata such as connector type, source path, raw indexes, and
  available section records;
- normalized text and optional structured sections.

Outputs:

- ordered source units with stable ids or indexes;
- unit type, title, text span, source range, raw indexes, and structural path;
- unitization warnings such as missing structure or forced paragraph grouping;
- structural hints passed to source normalization and source digest projection.

## Contract

Source Unitization is deterministic. It preserves source-local order and records
where each unit came from. It does not decide wiki page boundaries, write
actions, claim importance, relation meaning, or final Markdown prose.

The source normalization agent may clean labels, remove process noise, and
produce compact wording from the provided units. It should preserve the
deterministic unit boundaries unless the source type is inherently unstructured.

The source digest audit page is generated from the unitized source contract.
Knowledge atom evidence should cite source units rather than broad whole-source
text whenever a unit exists.

## Source Type Matrix

Source Unitization is source-type aware. The rule for each type should follow
the strongest stable structure already present in the material.

| Source type | Unitization rule | Reason |
| --- | --- | --- |
| Markdown / document | Split by heading sections, preferring `#`, `##`, and `###` | Headings naturally express local topics. |
| PDF / Office parsed Markdown | Split by headings, page spans, table blocks, and figure caption blocks | Rich documents use pages, sections, tables, and figures as evidence-location units. |
| Chat session | Split by complete Q/A turns or continuous topic spans | A single user or assistant message can be incomplete; the turn is the stable semantic unit. |
| Codex / Claude Code / OpenClaw records | Split by user-task turn groups and filter tool noise | Tool events are dense; reusable knowledge usually forms around the user's task. |
| Hermes ordinary conversation | Split by topic span or user question | A user question usually opens the knowledge boundary in conversation. |
| Selected excerpt / manual extract | Preserve one selected unit, or split by explicit user-selected fragments | User selection is already an intentional boundary. |
| Plain text | Split by paragraph groups | Without headings, paragraph grouping is the weakest stable structure. |
| Code file | If supported, split by function, class, or documentation/comment block | Code knowledge boundaries are usually symbol-level. |
| Web / HTML | Split by DOM heading and article section | Web pages usually expose structure through headings and sections. |
| Table / CSV | Split by sheet, table, or row group | Single rows may be incomplete; sheets, tables, or groups are more stable. |
| Image OCR | Split by OCR block or page region | OCR evidence needs region-level traceability. |

The matrix defines the mature target. Individual connectors can implement the
same contract incrementally as long as reports expose which rule was applied
and which fallback was used.

## Relationship To Segmentation

Segmentation protects model budget. Unitization protects evidence traceability.
The chain is:

```text
SourceDocument
  -> checkpoint window
  -> source segmentation
  -> source unitization per full source or segment
  -> source normalization
  -> source digest audit
  -> knowledge atom extraction
```

For long sources, aggregation remaps segment-local unit indexes into
source-level unit indexes before page planning:

```text
segment unit 0.0
segment unit 0.1
segment unit 1.0
  -> source unit 0
  -> source unit 1
  -> source unit 2
```

## Acceptance Criteria

- Markdown unitization uses headings before paragraph grouping.
- A short structured Markdown note such as `A2A.md` can produce multiple source
  units even when it remains a single segment.
- Chat unitization preserves complete turn groups and stable raw indexes.
- Source digest pages list deterministic source units.
- Knowledge atom evidence can point to source unit ids or indexes.
- Reports show unit count and unitization warnings separately from segment count
  and segmentation warnings.
- Page planning receives source-level atoms after unit aggregation; it does not
  receive raw full-source text solely to compensate for missing unit structure.

## Implementation Phases

Implementation order should follow current product value while preserving the
full matrix as the target contract.

### Phase 1: Current Knowledge Sources

- Markdown / document heading sections.
- PDF / Office parsed Markdown headings, page spans, table blocks, and figure
  caption blocks when the parser provides them.
- Codex, Claude Code, OpenClaw, Hermes, and ordinary chat turn groups.
- Selected excerpt units.
- Plain text paragraph groups.
- Report fields for unit count, unitization rule, fallback rule, and warnings.
- Tests proving segment count and source unit count can differ.

### Phase 2: Structured And Web Sources

- Web / HTML DOM heading and article-section units.
- Table / CSV sheet, table, and row-group units.
- Image OCR block and page-region units.

### Phase 3: Code-Aware Sources

- Code file symbol units by function, class, or documentation/comment block.
- Language-specific symbol extraction can be added behind the same source unit
  contract when code becomes a core source type.
