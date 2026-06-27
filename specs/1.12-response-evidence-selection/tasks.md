# 1.12 Response Evidence Selection Tasks

## P0 Selector Contract

- [x] Add rejected candidate schema.
- [x] Add deterministic `AnswerSetSelector`.
- [x] Replace presenter-local selection helpers with the selector.
- [x] Expose selection decisions in query trace.
- [x] Add tests for source demotion, broad multi-page selection, and redundant
  candidate rejection.
- [x] Freeze runtime query response, chat evidence pack, and public citation
  presentation contracts.

## P1 Quality Tuning

- [ ] Add fixture-based query cases for common KnoArbor questions.
- [ ] Review selector output against real vault queries.
- [ ] Tune structural thresholds only from observed failures.

## Deferred

- [ ] Optional LLM rerank for low-confidence cases.
- [ ] Per-vault personalization from feedback history.
- [ ] UI visualization of rejected candidates.
