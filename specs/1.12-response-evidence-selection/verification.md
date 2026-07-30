# 1.12 Response Evidence Selection Verification

## Lifecycle

Superseded by `1.38-semantic-indexed-raw-query`; these checks are historical.

## Automated

- Source record pages are source role by default for ordinary questions.
- Source record pages can be primary for provenance questions.
- Broad queries select multiple answer-bearing pages when evidence dimensions differ.
- Redundant pages are reported as rejected candidates.
- Query trace includes selection metadata.
- Runtime contract constants cover `wiki_query.v1`,
  `chat_evidence_pack.v1`, answer page roles, and ingest observation steps.
- Public citations are resolved from answer references and validated evidence,
  with hidden evidence counted separately.

## Manual

- Ask broad questions in Chat and verify the answer uses a small set of
  relevant pages rather than listing all similar pages.
- Ask source/provenance questions and verify source record pages are surfaced.
- Ask noisy related-page questions and verify unrelated candidates are not sent
  as primary evidence.
