# ADR 0003: Semantic-Indexed Raw-Grounded Answering

## Status

Partially Superseded by ADRs 0006 and 0007

## Context

KnoArbor ingest produces raw sources, source-oriented audit data, semantic
atoms, wiki pages, query context packs, and chat answers. Earlier flows could
use wiki page prose, source record summaries, claims, entities, and relations as
answer material. That made answers convenient, but it also allowed model-created
summaries to become the factual layer for later answers.

The durable question is what material is allowed to support a factual answer.
If page prose or atom text becomes answer evidence, then each ingest compile can
silently reshape the source. If raw-only retrieval is used, the system loses the
value of maintained wiki objects and semantic indexes.

## Decision

KnoArbor uses semantic-indexed raw-grounded answering:

```text
Raw Source
-> Source Processing Record / Source Units
-> Semantic Atoms with explicit evidence edges
-> Claim-centered atom retrieval
-> Exact active source-unit resolution
-> Raw Evidence Pack
-> Answer From Raw Evidence Only
```

Claims, entities, relations, synthesis, and source metadata are semantic locator
elements. Claims are the central retrieval result; entities and relations route
to claims through explicit references. Wiki pages remain readable navigation
projections and do not participate in default retrieval. None of these derived
elements is factual answer material under the raw-grounded policy.

The allowed factual material is:

- `raw_evidence` selected from indexed source units;
- direct `source_unit` excerpts with stable source identity, ranges, hashes, and
  processing record ids.

The disallowed factual material is:

- wiki page body prose;
- wiki synthesis or summary text;
- atom claim text when it is not paired with raw evidence;
- entity or relation summaries;
- source record markdown prose.

Legacy source-record Markdown is readable historical projection material. The
current durable audit path is the structured source processing record plus its
source units and evidence-backed atoms; current ingest does not generate a
second source-record Markdown artifact.

## Consequences

Positive consequences:

- Chat and query answers stay faithful to original material instead of derived
  page prose.
- Wiki pages still matter as semantic locator objects and human-readable
  navigation.
- Reports can audit one raw source through one structured processing record and
  all indexed source units.
- Provenance does not depend on source-record Markdown.

Costs:

- Query and chat context packs must include enough raw evidence for the final
  answer; otherwise they must report an evidence gap.
- Ingest must preserve stable source unit ids, content hashes, and ranges.
- Legacy source pages remain readable through the reserved navigation
  namespace but do not participate in factual publication or default query.

## Alternatives Considered

### Page-First Answering

Rejected because wiki prose and synthesis are model-produced projections. They
are useful for reading and retrieval, but they should not be the final factual
material.

### Independent Raw Retrieval

Rejected because it bypasses KnoArbor's maintained semantic layer and creates a
second retrieval authority. Raw units are resolved only after an explicit
claim evidence edge is selected.

### Merge Source Record And Wiki Page

Rejected as the core model because source audit and knowledge reading have
different identities. A page can remain readable, but source processing must
remain source-oriented and one-to-one auditable.

## Verification And Follow-Up

- Query context packs must include raw evidence blocks and must not include wiki
  page body prose as factual context.
- Chat evidence packs must pass raw evidence and locator pages separately.
- Ingest reports must show source processing records and raw evidence counts.
- Current ingest writes deterministic projection pages under `wiki/pages/` and
  does not write source-record Markdown under `wiki/sources/`.

## Supersession

[ADR 0006](0006-source-separated-chat-answering.md) replaces only the rule that
every Chat knowledge answer must be raw-grounded. General-model Chat answers
are a separate, non-grounded source mode and cannot create knowledge-base
citations or become raw authority through automatic Chat ingest.

[ADR 0007](0007-unified-active-raw-evidence-retrieval.md) replaces the rule that
an explicit claim evidence edge is the only path allowed to locate Raw. Atom
and claim signals remain preferred semantic locators, while active Raw-unit
lexical recall becomes a second locator channel. Both channels converge on the
same active Raw factual authority defined by this ADR.
