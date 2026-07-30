# ADR 0016: Direction-First Retrieval Planning

## Status

Partially Superseded

## Context

Document and top-level chapter regions provide a compact first-stage locator,
but an unchanged conversational question is not always a useful lexical
expression inside the selected material. Cross-language questions and
follow-ups containing pronouns or ellipsis can select the correct region while
still failing BM25 recall. Replacing the original question entirely would
create a fragile model-owned retrieval authority.

## Decision

Chat makes one dialogue-aware retrieval-planning call over the latest question,
the dialogue-only history, and `active_corpus_outline.v1`. The outline includes
one derived `language_hint` per document and chapter but no source body or
semantic atoms. The model selects exact visible regions and writes one
standalone, region-targeted search expression per region. It may resolve
follow-up references and translate into the target material's dominant
language. Dependent or presentation-only follow-ups preserve the recent factual
subject/source scope, and explicit inventories or comparisons cover every
named branch.

Code validates every region ID and clear compliance with `zh`/`en` language
hints. For each selected region it sends both the
unchanged latest question and the model-authored expression to one Query batch.
Those variants form one region group and share a single 12-parent BM25/RRF
window. Variants are alternative formulations: one Raw parent keeps its best
rank contribution inside the group instead of gaining repeated votes merely
for matching both formulations. Query then deduplicates active Raw identities across region groups and
applies the 16-parent global window. If both variants normalize to the same
text, code sends only one expression. Empty or unavailable planning falls back
to one unscoped unchanged expression.

The planner cannot choose algorithms, inspect candidates, admit evidence,
declare no-match, or answer. Query remains model-free and remains the only
owner of recall, fusion, result windows, structural evidence selection, and
active Raw resolution. Ingest remains unchanged.

## Consequences

- Region selection and conversational/cross-language query clarification use
  the same model call.
- The original question remains a retrieval guardrail without doubling the
  evidence allowance.
- Model cost is independent of candidate count and normally remains one
  planning call plus one answer call.
- Weak lexical overlap may still reach grounded synthesis; unsupported claims
  remain subject to support-span validation and explicit answer gaps.

## Supersession

This ADR supersedes ADR 0014 only where it prohibited model-authored regional
search expressions. It supersedes ADR 0015 only where the 12-parent window was
defined per expression rather than per region group. Their region boundary,
model-free Query, BM25/RRF, Raw authority, and global-window decisions remain
accepted.

ADR 0017 supersedes only the outline field-selection decision that excluded
all semantic atoms. The planner now receives one complete source-level
synthesis per document as locator-only context; every other model, Query, and
Raw-authority boundary in this ADR remains accepted.

## Alternatives

- **Use only the rewritten expression:** rejected because a model rewrite can
  omit an identifier or distort user intent.
- **Give each variant its own result window:** rejected because query
  clarification would double regional evidence volume.
- **Judge every candidate with a model:** rejected because token and latency
  cost would grow with recall volume.
- **Move rewriting into Query:** rejected because Query is the deterministic,
  provider-independent retrieval owner.

## Verification

- cross-language and conversational follow-up plans produce standalone
  region-targeted expressions while retaining the literal question;
- invalid regions are rejected and planner failure uses one unscoped literal
  expression;
- literal and rewritten variants in one region jointly retain at most 12
  deduplicated parents, and a shared generic match cannot outrank a specific
  match merely by receiving two votes;
- multiple region groups jointly retain at most 16 active Raw parents;
- the planner sees dialogue and locator metadata but no Raw, Claim, Entity,
  Relation, attachment, revision, or evidence payload;
- the fixed six-document retrieval suite records reachability, evidence count,
  packet size, latency, and planner usage without invoking candidate-level
  model judgment.
