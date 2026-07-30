# 1.26 Raw-Grounded Ingest Chain Design

## Status

Implemented revision to the 1.26 baseline, including retained local Markdown
and Obsidian image assets.

## Decision Summary

The ingest product chain is:

```text
SourceDocument
  -> EvidenceUnit[]
  -> UnitBatch[]
  -> ModelExtraction.v7
  -> KnowledgeAtomBatch.v3
  -> LinkedKnowledgeAtomBatch.v3
  -> PublishedKnowledgeRevision.v2
  -> ExtractionInventoryProjection
```

Raw content remains the primary reading surface. The model contributes only
semantic judgments. Deterministic code establishes durable evidence, identity,
files, attachments, and presentation.

## Element Ownership

| Element | Created by | Validated or derived by | Persisted in | Projected as |
| --- | --- | --- | --- | --- |
| Entity name | Model | Source occurrence and evidence validation | `knowledge.json` | Entity label |
| Entity aliases | Model | Occurrence and conflict validation | `knowledge.json` | Optional alias text |
| Entity unit positions | Model | Resolved to stable evidence references | Never persisted | Entity provenance |
| Claim text | Model | Grounding validation | `knowledge.json` | Claim text |
| Claim entity positions | Model | Resolved through source contributions and 1.27 | Never persisted | Retrieval links |
| Claim evidence quote | Model | Exact source occurrence and sufficiency validation | Never persisted | Evidence excerpt/location |
| Relation endpoints | Model | Reference closure and canonical linking | `knowledge.json` | Display triple |
| Relation predicate | Model | Normalization and support validation | `knowledge.json` | Display predicate |
| Relation evidence | Code | Union of supporting-claim evidence | `knowledge.json` | Derived evidence navigation |
| Synthesis | Model | Language, size, and segment composition | `knowledge.json` | Retrieval locator |
| Ambiguities | Model | Position validation and deduplication | `diagnostics.json` | Hidden from ordinary body |
| IDs, hashes, paths | Code | Deterministic contract rules | Source/knowledge/manifest | Hidden internal identity |
| Attachment metadata | Connector/processor/code | Schema and file validation | `source.json` | Selected metadata |
| Thumbnail | Code | Local asset validation | `source.json` reference | Optional preview |

## Source-Language Fidelity

Code derives one coarse `source.language` hint and one local language hint for
each source unit. The model uses the local supporting wording as authority:
Chinese facts produce Chinese metadata, English facts produce English
metadata, and bilingual or mixed facts may remain mixed. Document-level
language never authorizes output-wide translation. This policy is owned by the
semantic extraction prompt. Deterministic compilation validates grounding,
references, and evidence, but performs no script-ratio language classification
and does not reject metadata for a language mismatch.

## Contract 1: ModelExtraction.v7

```text
schema_version: index_metadata_extract.v7
entities[]
  name
  aliases[]
  unit_positions[]
claims[]
  text
  entity_positions[]
  evidence[]
    unit_position
    quote
  relations[]
    subject_entity_position
    predicate
    object_entity_position
synthesis_topics[]
ambiguities[]
  kind
  description
  unit_positions[]
```

Every position is a strict non-negative integer addressing an array in the
current request or response. Claim evidence quotes are transient verbatim source
selections; code validates their source occurrence and creates the
persisted evidence object, excerpt, hash, and character range. The contract
contains no internal ID, persisted evidence object, file field, canonical
entity, attachment, confidence score, offset, or runtime instruction.

Repeated source wording and overlapping quotes are valid. When one quote occurs
more than once in its unit, code uses the first occurrence in source order as
the deterministic presentation location. Multiple claims may reuse the same
quote without sharing claim identity.

### Canonical Evidence Text

The persisted Raw unit is the factual text authority. Model selection and code
validation share one deterministic evidence view derived from that unit:

- a single layout line break at an East Asian attached-text boundary is
  projected without a space;
- a single layout line break at other text boundaries is projected as one
  ASCII space;
- blank lines remain hard barriers;
- horizontal whitespace, punctuation, case, Unicode characters, and wording
  remain unchanged;
- no OCR correction, edit distance, cross-unit search, or model retry belongs
  to evidence alignment.

Each projected character retains its Raw-unit character range. A successful
quote maps back to the enclosing Raw slice, so persisted evidence contains the
original text, including any layout line break. Character ranges are Unicode
code-point half-open ranges in the persisted Raw unit coordinate space. The
external source file's byte layout is outside this contract.

Claims own relations and provide their semantic support. Code includes each
accepted relation endpoint in its parent claim's entity references, derives
relation evidence from the parent claim, rejects unknown endpoints and
self-relations, and merges identical directional triples across claims. The
model does not emit relation evidence or supporting-claim references.
Relation predicates remain open source-language phrases. Structural grounding,
distinct endpoints, and parent-claim ownership define validity without a
predefined relation vocabulary.

## Synthesis Semantics

`synthesis` is one or two compact sentences that locate the source scope and
main supported themes for retrieval. It does not serve as a comprehensive
summary and does not replace raw reading.

For a single batch, the model string is retained after validation. For multiple
batches, code joins unique non-empty batch syntheses in source order. There is
no consolidation model call. The projection and retrieval layer consume the
same persisted synthesis string.

## Contract 2: KnowledgeAtomBatch.v3

```text
source_identity
entity_contributions[]
  contribution_key
  source_name
  aliases[]
  evidence_refs[]
claims[]
  claim_key
  text
  entity_contribution_keys[]
  evidence_refs[]
relations[]
  relation_key
  subject_contribution_key
  predicate
  object_contribution_key
  supporting_claim_keys[]
  evidence_refs[]              # derived from supporting claims
synthesis
```

The compiler creates this source-local type directly from accepted candidates.
It contains no model positions and no vault-global entity IDs. Specification
1.27 links it by filling canonical IDs without introducing a duplicate payload
whose fields have identical meaning.

## Validation And Merge

- Unknown source-unit positions reject the containing candidate.
- An entity whose primary source-written name does not occur in its cited
  evidence rejects only that entity candidate.
- An invalid evidence quote rejects its parent claim, not the source or other
  claims. Every declared quote on an accepted claim must validate.
- Unsupported aliases reject only the alias.
- Invalid claim entity positions reject only those references when the claim
  itself remains grounded.
- Unknown relation endpoints or supporting claims reject the relation.
- Relations owned only by rejected claims are rejected. Shared relations keep
  accepted supporting claims and recompute their evidence union.
- A relation requires one supporting claim containing both endpoints.
- Relation evidence is the stable union of supporting-claim evidence.
- Entity, claim, and relation keys use normalized semantic content plus stable
  source provenance; segment indexes never enter identity.
- Overlap duplicates union evidence and aliases while preserving source order.
- Rejections have one typed reason in `diagnostics.json`; no fallback relation
  is inferred from co-occurrence.
- After candidate-local filtering, one deterministic compiler-integrity check
  enforces source identity, unique atom identity, evidence ownership, and
  reference closure. A violation is an internal source failure, not a quality
  result or a retryable model-output error.
- A source with some accepted claims publishes normally with diagnostics. If
  claim candidates exist but all are rejected, Raw is published without claim
  or relation facts and the source result is partial and non-retryable.
- Evidence hydration rejects invalid persisted ranges. It never widens a bad
  claim range to the complete Raw unit.

## Contract 3: PublishedKnowledgeRevision.v2

The factual revision contains two typed payloads and one non-factual diagnostic
payload:

```text
source.json
  schema_version
  source identity and revision
  normalized source metadata
  source units and ranges
  attachments[]
    attachment identity
    path/type/hash/size
    topic/description
    source range
    thumbnail reference

knowledge.json
  schema_version
  source/revision identity
  synthesis
  entity_contributions[]
  canonical entity snapshots[]
  claims[]
    stable ID
    text
    canonical entity IDs
    entity display snapshots
    evidence[]
  relations[]
    stable ID
    canonical endpoint IDs and display snapshots
    predicate
    supporting claim IDs
    derived evidence[]

diagnostics.json
  schema and compiler versions
  candidate/accepted/rejected counts
  bounded typed rejection details
  ambiguities
```

`source.json` and `knowledge.json` are factual authority selected by the source
head. `diagnostics.json` is immutable audit material but is excluded from
factual retrieval.

There is no second quality-gate payload, approved-segment list, or aggregate
rejected-annotation warning. Compiler diagnostics are the single explanation
for candidate-local rejection.

## Attachment Policy

Attachment metadata originates in connectors, document processors, sidecars,
or deterministic filesystem inspection. Existing caption, alt text, OCR/VLM
processor output, topic, and description remain attributable source metadata.
Privacy redaction is field-aware at this boundary: descriptive values may be
redacted before semantic use or display, while content hashes, retained paths,
attachment IDs, MIME types, thumbnails, and connector/source identity bypass
text-pattern substitution. A phone-number detector therefore cannot rewrite a
substring of a content-addressed filename or hash.

For local Markdown, standard image links and Obsidian image embeds are two
source syntaxes for the same attachment contract. The Markdown connector
resolves either syntax only within one explicit source root carried with source
discovery. Folder input resolution supplies the selected input folder to every
prepared Markdown document, file input supplies the selected file's parent,
and configured Markdown connectors retain the root that discovered each source
reference. The connector does not reconstruct this root from each Markdown
file. A path-qualified reference resolves to one file under that root; a
filename-only Obsidian embed is accepted only when exactly one matching image
exists. Missing and ambiguous references do not create attachment facts.

The immutable input-generation writer is the ownership handoff from an
external source file to vault storage. Before serializing `SourceDocument`, it
copies each validated local attachment to a content-addressed path under
`raw/derived/assets`, verifies an existing target by hash, and replaces the
external path in the document attachment metadata with the vault-relative
reference. Consequently `source.json`, projection rebuild, backup, and Raw
display never depend on the original source tree remaining available.

Persisted Raw Markdown remains byte-for-byte source text. The Raw page service
derives display Markdown by mapping a recognized Obsidian embed to its retained
attachment reference. Ordinary `[[Wiki links]]` remain navigation links;
unresolved `![[image embeds]]` remain literal source notation rather than being
converted into a broken Wiki-image URL. This display transformation is derived
and never enters editing, evidence, or factual authority.

For an image that is directly renderable, its retained local asset may serve as
the thumbnail. For a supported document/media type, code may generate a local
thumbnail under the raw derived asset area. The fact payload stores a relative
reference and hash, not embedded image bytes. Missing topic, description, or
thumbnail remains empty. Visual semantic enrichment, if introduced later,
requires its own explicit contract and provenance.

## Extraction Inventory Projection

The projection body is intentionally small:

```text
Title
Source metadata              # path, type, source revision when useful
Synthesis                    # retrieval locator
Claims
  human label Cn
  claim text
  evidence excerpt
  structural/source location
Entities
  display name
  explicit aliases when present
Relations
  human label Rn
  subject, predicate, object
  supporting claim labels
Attachments
  thumbnail when available
  topic and description when present
```

The renderer assigns human labels from projection order. Internal IDs remain in
structured metadata only. Entity names are plain display text unless a concrete
target page exists. Empty optional values produce no fabricated description.
Ambiguities and rejection diagnostics remain available through diagnostic UI
or developer inspection rather than the ordinary page body.

## Implementation Boundaries

```text
ingest_auto.py
  document orchestration, unitization, segment scheduling, source outcome

ingest_compilation.py
  pure cross-segment merge and deterministic compiler-integrity validation

ingest_publication.py
  FactCommit construction, checkpoint cursor, session window, publication DTO

index_metadata_atoms.py
  transient model extraction to deterministic knowledge atoms

knowledge_evidence.py
  shared structural traversal for layer-owned evidence transformations
```

Structured synthesis topics remain arrays through model extraction and segment
compilation. Markdown rendering occurs only when constructing the persisted
knowledge batch. Evidence transformations share traversal code while raw,
revision, persistence, and hydration rules remain owned by their respective
boundaries.

## Physical And Runtime Handoffs

Specification 1.17 owns the stable physical tree:

```text
.knoarbor/facts/<source-key>/<revision-key>/
  source.json
  knowledge.json
  diagnostics.json
  manifest.json
```

Specification 1.37 stages the four files, verifies hashes, atomically publishes
the directory, updates the SQLite source head, and requests materialization.
The materializer reads only the active revision and can recreate the extraction
inventory and machine indexes without a model.

## Migration

The implementation migrates active `source_revisions/generations/**` payloads
to the fact tree before switching readers. Existing
`source_processing_record.json` maps to `source.json`; existing
`knowledge_atom_batch.json` maps to `knowledge.json`; diagnostics and manifests
are rewritten under their versioned schemas. Migration is restartable,
integrity-checked, and does not call a model. The old reader and writer are
deleted after migration verification; no permanent dual authority remains.

## Rejected Alternatives

- Restoring `summary`: it duplicates raw reading and changes synthesis from a
  locator into editorial content.
- Relation-authored unit positions: supporting claims already provide the
  complete evidence authority and duplicate positions can disagree.
- Model-authored excerpts or attachment descriptions: deterministic provenance
  would become probabilistic and untraceable.
- Entity Wiki links without a target page: presentation would create broken
  navigation from extraction metadata.
- A rich generated knowledge article: it competes with the raw-first product
  surface and adds unsupported prose.
- Keeping old and new fact paths as fallback readers: two factual authorities
  make recovery and backup semantics ambiguous.
