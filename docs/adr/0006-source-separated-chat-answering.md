# ADR 0006: Source-Separated Chat Answering

## Status

Partially Superseded by [ADR 0010](0010-automatic-chat-source-routing.md) and
[ADR 0019](0019-unified-final-chat-answer.md)

## Context

KnoArbor Chat currently treats claim-backed active raw evidence as the only
factual authority. This is the correct contract for questions about maintained
local knowledge, but it prevents the selected language model from answering a
question when the vault contains no relevant material.

Simply relaxing the grounded answer prompt would make local evidence and model
general knowledge indistinguishable. A boolean fallback marker would also be
insufficient: retrieval no-match, retrieval failure, direct product help, and
stream recovery have different meanings. Chat sessions can also be submitted
to ingest, so an unmarked general-model answer could otherwise return as a new
raw source and falsely acquire knowledge-base authority.

## Decision

Chat uses a code-owned, source-separated answer state machine.

Each request declares exactly one policy:

- `knowledge_only`: answer only from local raw evidence and report a gap when
  that evidence is absent;
- `knowledge_then_general`: try the same local retrieval path first and use
  model general knowledge only after code establishes a genuine no-match.

Each completed answer records exactly one mode:

- `knowledge_grounded`;
- `knowledge_grounded_with_gap`;
- `general_knowledge`;
- `knowledge_gap`;
- `clarification`;
- `direct_capability`.

Specification 1.38 produces typed query outcomes, including trustworthy
`no_match`. Specification 1.10 validates grounded semantic coverage and
produces the final Chat outcome. A general answer is allowed only for
`no_match` under `knowledge_then_general`. Partial evidence, clarification
needs, integrity errors, tool failures, cancellation, repeated planning, and
planning exhaustion never trigger general fallback.

Grounded and general answers use different synthesizers and different prompts.
ADR 0003 remains authoritative for `/query`, `knowledge_grounded`, and
`knowledge_grounded_with_gap`. General answers receive no raw evidence,
claims, projection prose, catalog descriptions, or locator metadata as factual
input. They produce no knowledge-base citations.

Answer policy, answer mode, and terminal retrieval outcome are public and
persisted turn fields. The renderer displays source identity on every assistant
turn. A model-written disclaimer is not the source of truth.

General, direct-capability, clarification, and knowledge-gap assistant turns
never participate in automatic Chat ingest or ingest-candidate scoring. They
also cannot be directly promoted through selected-message ingest. A user who
wants to retain general-model prose must first turn it into a separately
reviewed, user-authored source.

This is a development-stage replacement. Chat request, response, session, and
Chat-extract schemas advance together. The implementation does not retain v1
readers, dual-write fields, inferred legacy provenance, or migration adapters.
Development Chat data using the replaced schemas is cleared before the new
contract is exercised.

## Consequences

- Users can choose strict local answering or local-first answering with an
  explicitly marked general-model result.
- Local knowledge citations continue to mean active raw support.
- Retrieval failures remain visible instead of being hidden behind a plausible
  model answer.
- Sessions, retry, streaming, telemetry, and renderer restoration consume the
  same provenance object.
- Direct ingestion of general assistant prose is intentionally unavailable.
- Old development Chat sessions are disposable and are not readable through a
  compatibility path.
- Mixed local/general prose and Web Search require future source contracts and
  are outside this decision.

## Alternatives Considered

### Relax The Existing Grounded Prompt

Rejected because one answer would have two factual authorities without a
deterministic boundary or reliable citation meaning.

### Store `is_fallback`

Rejected because one boolean cannot distinguish no-match, system failure,
product help, fixed error text, and general-model generation.

### Mix General Knowledge Into Partial Grounded Answers

Rejected until answers have section-level provenance. The first version keeps
partial answers grounded and states the remaining gap.

### Re-Ingest General Answers After A Confirmation Dialog

Rejected because confirmation does not validate factual content. Promotion to
raw authority requires a separate reviewed source boundary.

### Preserve V1 Chat Data And Contracts

Rejected during development because dual readers and inferred provenance would
become a second policy path before the product contract stabilizes.

## Verification

- Router tests cover every policy and terminal-outcome combination.
- Grounded answers retain raw-only factual support and valid active citations.
- General answers have empty citations and never invoke the knowledge reference
  resolver.
- Retrieval and integrity failures cannot enter the general synthesizer.
- Stream final responses, persisted turns, retry, renderer restoration, and
  token ledger records agree on provenance.
- Automatic, session, and selected-message ingest reject non-grounded assistant
  turns.
- Contract tests reject replaced v1 Chat payloads and fixtures.

## Follow-Up

- Specifications 1.10 and 1.18 own implementation and focused verification.
- [ADR 0007](0007-unified-active-raw-evidence-retrieval.md) and specification
  1.38 own unified locator retrieval, active Raw resolution, and the calibrated
  trustworthy no-match prerequisite.
- Mixed-source answers and Web Search require separate accepted designs.
