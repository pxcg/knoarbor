# ADR 0010: Automatic Chat Source Routing

## Status

Superseded by [ADR 0019](0019-unified-final-chat-answer.md)

## Context

ADR 0006 introduced source-separated local and general answers together with a
per-request `knowledge_only` or `knowledge_then_general` selector. The source
separation remains necessary, but the selector exposes an internal routing
mechanism that users should not need to understand. Both choices execute the
same retrieval path and differ only after code has already established a
trustworthy local no-match.

Keeping the selector also duplicates one policy value through renderer state,
API requests, retry requests, provenance, session storage, telemetry, tests,
and documentation without adding evidence or safety information.

## Decision

Chat has one automatic, code-owned source router:

1. retrieve from the selected vault through specification 1.38;
2. answer from active Raw evidence when semantic coverage is sufficient or
   partial;
3. use the separate general synthesizer only after a trustworthy `no_match`
   and the packaged no-match quality gate, unless the user's question
   explicitly asks what the selected local document, source, material, or
   knowledge base says;
4. never use general synthesis for partial coverage, unavailable indexes,
   integrity or tool failures, cancellation, clarification, planning
   exhaustion, or resource exhaustion.

The composer exposes no answer-policy selector. Chat request, retry,
provenance, persisted session, token-ledger, and renderer contracts contain no
answer-policy field. They continue to carry answer mode, Query outcome, and
Chat outcome because those fields describe actual execution evidence.

The router deterministically classifies explicit local-source wording as a
local-evidence requirement. A trustworthy no-match for that scope produces a
knowledge gap. It never invokes general synthesis and therefore cannot affirm
a false premise or attribute pretrained knowledge to the local material.

The development contract advances to `chat_request.v3`, `chat_response.v3`,
`chat_session.v3`, and `chat_session_retry_request.v3`. V2 Chat payloads and
session records are not read, inferred, or migrated.

ADR 0006 remains authoritative for source separation, grounded evidence,
general-answer isolation, citations, and Chat-ingest eligibility. This ADR
replaces only its per-request policy choice and policy persistence.

## Consequences

- Users ask questions without choosing an internal routing mode.
- Local evidence remains the first and preferred factual source.
- A genuine local no-match remains distinct from retrieval failure.
- A source-scoped local no-match remains distinct from an ordinary question
  that may be answered from model general knowledge.
- General answers remain visibly labeled and citation-free.
- Removing the redundant field simplifies retry, persistence, telemetry, UI,
  and contract tests.
- Development sessions written with V2 are disposable.

## Alternatives Considered

### Hide The Selector But Keep The Policy Field

Rejected because a constant request value and persisted policy would retain a
second, meaningless state owner and compatibility surface.

### Always Ask The General Model After Partial Coverage

Rejected because a single answer would mix factual authorities without
section-level provenance.

### Treat Retrieval Failure As No-Match

Rejected because it would conceal unavailable or invalid local evidence behind
a plausible model answer.

## Verification

- Contract tests reject V2 and any V3 payload containing an answer-policy
  field.
- Router tests prove only trustworthy no-match can select general synthesis.
- Router tests prove explicit local-source questions cannot select general
  synthesis after no-match.
- Grounded, partial, error, cancellation, and resource outcomes retain their
  existing answer modes and safety behavior.
- Sync, stream, retry, persistence, token ledger, and renderer restoration
  agree on policy-free provenance.
- Searches find no live answer-policy selector, type, field, default, or
  persisted record outside superseded historical material.

