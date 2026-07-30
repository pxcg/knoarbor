# 1.10 Wiki Chat Tasks

## Established Linear v4 Runtime

- [x] Preserve the unchanged latest question in every selected region group.
- [x] Derive the compact document/top-level-chapter outline from active source
  processing records.
- [x] Invoke one dialogue-aware Retrieval Planner before the Query batch.
- [x] Accept only exact visible region IDs and compile typed Query scopes in code.
- [x] Generate one standalone expression per selected region and group it with
  the unchanged question in one Query-owned batch.
- [x] Remove the recursive planner/read/answer loop.
- [x] Forward Query evidence without Chat-owned ranking or truncation.
- [x] Use one whole-response authority for candidates and no-match.
- [x] Replace dimension coverage with flat selected support and optional gap.
- [x] Keep support-span validation and code-owned citation placement.
- [x] Keep Raw-grounded, general, or gap semantics under model judgment while
  code validates one non-mixed authority and derives provenance.
- [x] Delete the packaged no-match gate, local-evidence regex, and physically
  separate grounded/general answer classes and prompts.
- [x] Delete the candidate-level model judge; Query remains the sole evidence
  admission owner.

## State And Compatibility

- [x] Remove topic-anchor and turn-intent services.
- [x] Remove dimension and coverage schemas.
- [x] Remove retrieval continuation and Chat-owned cursor state.
- [x] Remove public `max_turns` and model/tool-call count limits.
- [x] Advance request, response, retry, and session contracts to v4.
- [x] Add explicit v3 session migration to v4.
- [x] Preserve complete dialogue-only history without evidence replay.
- [x] Reject invented region IDs and preserve unscoped-query degradation.
- [x] List canonical sessions from summary prefixes without materializing turn
  transcripts or traces.
- [x] Compact duplicated Raw payloads when legacy v3 traces enter the v4 view.
- [x] Discard duplicated migrated session-level trace when authoritative
  turn-local traces exist.
- [x] Paginate summary-only session listing and let the sidebar reach every
  persisted older session.
- [x] Invalidate citation preview state and in-flight reads on session or vault
  transition.
- [x] Group public citation markers by Raw source unit while preserving every
  disjoint answer-selected range inside its compact citation locator.
- [x] Group citation sources by document and highlight every cited span while
  retaining per-excerpt focus.
- [x] Resolve persisted citation ranges from immutable source units on demand
  without storing Raw excerpts or falling back to full-Raw coordinate slicing.

## Product Parity

- [x] Preserve streaming, cancellation, retry, deletion, session ingest, and
  duplicate-request protection.
- [x] Preserve dynamic image capability, generated-image storage, and source
  image presentation.
- [x] Keep image requests on the ordinary mainline, let Answer Decision author
  one optional semantic `generated_image_prompt`, run generation before
  Response Composer, and let the composer position successful generated
  visuals.
- [x] Make source-image semantics part of Raw support, with transient
  visual-reference placement, same-Raw validation, no durable model-visible
  attachment identity, and no generated-image substitution.
- [x] Replace block-tail source-visual lists with one validated standalone
  placeholder that preserves the model-selected paragraph position while
  keeping stored Markdown and paths code-owned.
- [x] Add a code-owned non-evidence provenance label to optional generated
  images.
- [x] Preserve multi-vault identity and Raw-grounded citations.
- [x] Update renderer contracts and request construction.
- [x] Update architecture, API, prompt, and verification documentation.
- [x] Run focused backend, renderer, governance, and residual-state checks.

## Answer Decision And Composition Revision

- [x] Replace unified Final Answer with one fixed Answer Decision followed by
  one Response Composer call for candidates and trustworthy no-match.
- [x] Add strict request-local schemas for the five-field decision and ordered
  composer items.
- [x] Validate mode, support, selected-visual ownership, complete material
  coverage, exactly-once selected-visual use, and image-generation
  authorization in code.
- [x] Project only selected exact Raw and selected visual semantics into
  request-local material IDs for Response Composer.
- [ ] Add one code-owned source label and authoritative Raw span order to every
  composer material.
- [ ] Clean model-visible assistant history of code-rendered citations and
  images without truncating substantive dialogue.
- [ ] Enforce continuous citation blocks, source visuals after owner text,
  reader-facing gaps, and rejection of material IDs in prose.
- [x] Preserve public response/session v4, citation, image artifact, retry,
  streaming, cancellation, and persistence contracts.
- [x] Delete the unified Final Answer prompt and request-local schema after the
  replacement path is complete.
- [x] Update semantic phase telemetry and focused fixtures.
- [x] Run the complete affected validation and 70-case Chat Gold structural
  gate; keep live-model execution as a separately reported observation.

## Comprehensive Acceptance v2

- [x] Freeze v1 as historical evidence and define one uniform v2 corpus/Gold
  schema aligned with Retrieval, Answer Decision, and Response Composer.
- [x] Add the controlled same-title version pair and only the distinct cases
  required for version conflict, harder authority routing, partial gaps, and
  adversarial dialogue history.
- [x] Replace stale six-document wording, meta-authored runtime prompts,
  duplicated low-information questions, and unowned privacy expectations.
- [x] Add deterministic definition and reviewed-live-result validation with
  separate stage and evidence reporting.
- [x] Update focused tests and English/Chinese maintainer documentation.
- [x] Run focused tests, affected validation, documentation governance, link
  checks, and diff hygiene before closure.
