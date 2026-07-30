# 1.26 Raw-Grounded Ingest Chain Requirements

## Status

Implemented extraction, fact-file, projection, and retained local-image
revision. Automated and isolated real-provider verification are complete.

## Ownership

This specification owns semantic extraction, deterministic compilation, the
persisted knowledge payload, and source extraction projection content.
Specification 1.27 owns canonical entity identity. Specification 1.17 owns
physical vault paths. Specification 1.37 owns atomic factual publication,
source heads, recovery, and materialization.

## Product Assumptions

KnoArbor is a local personal knowledge application. The original raw content
is the primary reading surface. Ingest adds compact semantic locator metadata
that helps retrieval and lets a user inspect what was extracted from the raw
source. It does not author a replacement knowledge article.

## Goals

1. Ask the model only for judgments that require semantic understanding.
2. Let the model select the smallest sufficient verbatim claim evidence, then
   generate identity, validated ranges, files, attachments, and presentation
   through deterministic code.
3. Present one deterministic evidence text view to both the model and the
   compiler. Resolve supported layout line breaks before model selection while
   preserving wording, punctuation, horizontal whitespace, and hard boundaries.
4. Preserve `synthesis` as a retrieval locator rather than a document summary.
5. Persist one clear source payload, one clear knowledge payload, and separate
   audit diagnostics per factual revision.
6. Render a minimal extraction inventory containing synthesis, claims, claim
   evidence, entities, relations, selected source metadata, and attachments.
7. Keep raw content authoritative and every projection model-free and
   rebuildable.

## Non-Goals

- Generating a polished replacement article or editorial summary.
- Model-authored IDs, hashes, paths, persisted evidence objects or offsets,
  attachment metadata, thumbnails, storage state, or Markdown.
- A second model call for cross-segment consolidation.
- Visual interpretation of otherwise undescribed attachments in the base
  ingest contract.
- Showing provider, task, retry, rejection, or materialization internals in the
  ordinary projection body.
- Distributed or enterprise-scale ingest behavior.

## Required Invariants

### R1. Raw Is The Reading Authority

The UI opens and presents normalized raw content as the primary document view.
The source projection is an extraction inventory and never becomes answer
evidence or a substitute for raw content.

### R2. Model Output Is Minimal And Semantic

The model returns only source entities and aliases, atomic claims, the smallest
sufficient verbatim source quotes supporting those claims, directional
relations, retrieval-locator synthesis, ambiguities, and request-local
positions required to express grounding and semantic associations.

### R3. Code Owns Derivable Structure

Code validates every model-selected quote against its source unit and owns all
IDs, hashes, paths, ranges, persisted excerpts, canonical linking,
deduplication, evidence construction, relation evidence, attachment metadata,
thumbnails, manifests, persistence, and projection formatting. Missing quotes
reject the containing claim instead of widening to the source unit or failing
other candidates. Repeated and overlapping quotes remain valid; repeated text
maps to its first source occurrence deterministically.

### R4. Relation Evidence Has One Authority

A relation references its endpoints and supporting claims. Its evidence is the
deterministic union of accepted supporting-claim evidence. The model does not
return a second relation-level `unit_positions` field.

### R5. Synthesis Is A Retrieval Locator

`synthesis` briefly identifies source scope and the supported themes useful for
retrieval. It is not renamed to `summary` and is not expected to reproduce the
source narrative.

### R6. Evidence Uses Stable Source Units

Model positions and quotes are transient. Code resolves each occurring quote
to stable source-unit IDs, the original source substring, structural
paths, ranges, and hashes. Every accepted claim has at least one precise
evidence reference.

### R7. Attachments Remain Source Metadata

Attachment path, type, size, hash, topic, description, source range, and
thumbnail come from connectors, document processors, sidecars, or deterministic
asset processing. Missing semantic labels remain empty in the base contract.
Local Markdown image syntax supported by the source application, including
Obsidian image embeds, resolves against the source root selected by the ingest
request or connector configuration, is retained as a vault-owned asset, and is
represented by persisted attachment metadata. Folder ingest passes the input
folder as one shared source root for every discovered Markdown document; file
ingest passes the selected file's parent; configured Markdown connectors pass
the root that discovered each source reference.
Resolution never selects an arbitrary file when a reference is missing or
ambiguous, and persisted Raw text remains unchanged.
Privacy processing may redact descriptive attachment text supplied to a model
or public projection, but it never mutates attachment IDs, content hashes,
MIME types, retained relative paths, thumbnails, or connector/source identity.

### R8. Facts And Diagnostics Are Separate

Accepted source and knowledge payloads are factual authority. Ambiguities,
candidate rejection details, and model-call metrics are audit diagnostics and
do not enter factual retrieval. Candidate grounding failures reject only the
containing candidate. After candidate-local filtering, deterministic structural
postconditions are compiler invariants: a violation fails the source as an
internal integrity error rather than creating a second quality-gate result or
`rejected` lifecycle state. Compilation does not infer semantic conflict from
open source-language relation predicates or require every grounded entity to be
referenced by a claim or relation.

### R9. Projection Content Is Fixed And Minimal

The projection may contain title, source navigation, synthesis, claims with
evidence and source location, entities with explicit aliases, relations with
human claim references, selected source metadata, and attachments with existing
topic, description, and thumbnail. It contains no internal IDs or runtime
diagnostics in the ordinary body.

### R10. Empty Fields Do Not Create Fabricated Content

Empty synthesis, aliases, relations, attachment descriptions, or thumbnails
are omitted or represented with one neutral empty-state label. Code does not
invent text to make a section appear populated.

### R11. Merge Is Deterministic

Segment outputs merge in source order using stable evidence-backed keys. Merge
unions valid aliases, references, and evidence without a model call and without
depending on segment numbering or completion order.

### R12. Projection Is Rebuildable

The persisted source and knowledge payloads contain every field required for
Wiki, raw detail, graph, and retrieval projections. Rebuild performs no model
call and wall-clock time does not alter canonical output.

### R13. Semantic Metadata Preserves Source Language Locally

Document language is a coarse hint, not an instruction to translate every
semantic element into one dominant language. Each entity, alias, claim,
relation predicate, synthesis topic, and ambiguity follows the language of the
source wording it represents. A bilingual source may therefore publish
Chinese and English metadata together, and a genuinely mixed statement may
remain mixed. Technical terms retain their source-written form. This is a
semantic extraction instruction, not a deterministic publication gate: code
does not infer language from character ratios or reject otherwise grounded
metadata because its output language differs from the source hint.

## Acceptance Criteria

1. Prompt, model schema, compiler, persisted knowledge schema, and tests agree
   on one field ownership matrix.
2. Relation model output has no evidence position field; published relation
   evidence equals supporting-claim evidence union.
3. No model-local position survives factual compilation.
4. `synthesis` remains a retrieval locator throughout model, storage, and
   projection contracts.
5. Projection shows each claim with its source evidence and stable source
   location.
6. Attachment presentation uses observed metadata and deterministic local
   thumbnails only.
7. Projection contains no unconditional broken entity links.
8. Two rebuilds of one revision produce identical canonical content.
9. The revision artifact tree and every file payload match this specification
   and specifications 1.17 and 1.37.
10. A local Obsidian image embed with one matching source-root asset renders in
    the Raw view from a retained vault asset after the external source tree is
    unavailable; missing and ambiguous embeds remain unresolved without an
    arbitrary match, and ordinary Wiki links keep their navigation semantics.
11. Privacy redaction leaves every attachment machine identity byte-identical
    while still redacting sensitive descriptive text.
12. Chinese-only, English-only, and bilingual sources expose matching
    document/unit language hints; the extraction prompt requires local source
    language fidelity, and ingest does not apply a separate language-mismatch
    gate to model output.
13. Ingest emits no relation-conflict, unused-entity, or missing-synthesis
    gate; empty synthesis and independently grounded entities remain valid.
14. An entity is accepted only when its primary source-written name occurs in
    its cited evidence. A missing name rejects that entity candidate without
    failing grounded sibling candidates or introducing fuzzy matching.
15. Published diagnostics contain compiler candidate outcomes and ambiguities,
    but no duplicate quality-gate payload, approved-segment list, or aggregate
    rejected-annotation warning.
