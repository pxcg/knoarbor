# ADR 0013: Corpus-Guided Dual-Path Retrieval

## Status

Accepted

## Context

ADR 0012 simplified default Chat into one linear Raw-grounded answer flow. It
preserved the literal user question and allowed one dialogue-aware Query
Composer only after a trustworthy literal `no_match`.

That trigger is too late for semantic retrieval. A literal query can produce an
eligible lexical candidate without locating the best source, so the presence of
any candidate cannot prove that corpus-aware query composition is unnecessary.
Conversely, replacing the literal question with a model rewrite would make
recall depend on a stochastic interpretation from a model that does not know
the private corpus.

KnoArbor already has active source identities, source-unit structure, entity
aliases, relation predicates, and attachment metadata. These values can form a
compact active corpus catalog that helps a model use the vocabulary actually
present in the selected vault without promoting generated summaries or
projection prose to factual authority.

## Decision

Every default knowledge Chat turn uses one bounded dual-path retrieval plan:

```text
latest question + dialogue-only history
  -> build locator-only Active Corpus Catalog
  -> one corpus-guided Query Composer call
  -> one Query batch containing:
       q1: unchanged latest question
       q2..qn: approved complementary semantic expressions
  -> Query-owned fusion, structural evidence selection, and Active Raw reads
  -> one grounded or separated general answer stage
```

The literal latest question is immutable and always remains the first batch
expression. Composer failure or an empty valid composition degrades to the
literal expression alone. The Composer cannot select internal identities,
change vault scope, declare no-match, choose evidence, or answer the question.

The Active Corpus Catalog is a derived locator view over current active facts.
It may expose source display names, source types, structural headings, entity
names and aliases, relation predicates, and attachment labels. It excludes Raw
content, claim prose, internal revision identities, evidence handles, and
projection prose. Every catalog build is bound to the active source heads; it
is never factual answer material.

All approved expressions execute in one Query-owned batch. Query remains the
sole owner of recall, channel fusion, candidate reachability, evidence
admission, active revision resolution, and Raw reads. Chat does not perform a
second search after inspecting the first result and does not rank, filter, or
truncate Query evidence.

No vector provider is required. A future vector recall provider may contribute
signals behind the same Query batch and Active Raw evidence contracts.

## Model And Code Ownership

The model owns only:

- resolving dialogue-dependent wording into complementary natural-language
  retrieval expressions;
- using visible catalog vocabulary when it preserves the user's answer
  obligation.

Code owns:

- the unchanged literal expression and its first position;
- catalog construction from active facts and locator-only field selection;
- vault scope, active lifecycle, identities, deduplication, and validation;
- batch execution, fusion, structural evidence selection, Raw reads, typed outcomes, and
  no-match;
- answer routing, citation validation, retry, and persistence.

## Failure Semantics

- Catalog absence or an empty vault produces a valid empty catalog; the literal
  path still executes.
- Composer timeout, provider failure, invalid output, or an empty composition
  records a warning and executes the literal path only.
- One expression finding candidates does not hide failures from another
  required expression. Query owns the typed batch outcome.
- General answering remains eligible only after the completed combined batch
  returns trustworthy `no_match` under ADR 0010.
- Resource, index, integrity, cancellation, and oversized-evidence states never
  become no-match.

## Consequences

- Semantic retrieval becomes corpus-aware without allowing a rewrite to replace
  the original question.
- Literal false positives no longer suppress semantic query composition.
- Default Chat still performs one retrieval batch and one answer stage, with no
  iterative planner/read/answer loop.
- One additional model call is expected for ordinary knowledge turns. Its input
  is locator metadata rather than Raw factual content.
- Catalog growth must be solved inside the retrieval/index owner through
  hierarchical locator projection, not Chat-side evidence trimming.

## Supersession

This ADR supersedes only ADR 0012's rule that Query Composer runs after
trustworthy literal no-match. ADR 0012 remains authoritative for linear Chat,
single answer synthesis, no persisted retrieval continuation, and Raw-grounded
citations.

## Alternatives Considered

### Model Rewrite Before Literal Retrieval

Rejected because model wording could erase exact identifiers, source names, or
user scope.

### Invoke Composer Only After No-Match

Rejected because a weak literal candidate can prevent the semantic path even
when the correct source uses different terminology.

### Run A Second Retrieval Batch After Inspecting Literal Results

Rejected because it restores result-dependent Chat branching and doubles Query
orchestration. Both paths belong in one batch.

### Use Generated Wiki Or Summaries As Answer Evidence

Rejected because catalog and projection material are locators. Active Raw
remains the only local factual authority.

## Verification

- every ordinary knowledge turn invokes at most one Composer, one Query batch,
  and one answer stage;
- the batch always keeps the literal latest question as `q1`;
- approved catalog-guided expressions are deduplicated and cannot replace
  `q1`;
- literal hits still include corpus-guided expressions in the same batch;
- empty catalog, empty composition, invalid composition, and Composer failure
  retain literal retrieval;
- catalog payloads contain no Raw content, claim prose, revision IDs, evidence
  IDs, or projection prose;
- Query evidence and citations resolve only to current Active Raw.
