# 1.12 Answer Set Selection Verification

## Automated

- Source digest pages are source role by default for ordinary questions.
- Source digest pages can be primary for provenance questions.
- Broad queries select multiple answer-bearing pages when facets differ.
- Redundant pages are reported as rejected candidates.
- Query trace includes selection metadata.

## Manual

- Ask broad questions in Chat and verify the answer uses a small set of
  relevant pages rather than listing all similar pages.
- Ask source/provenance questions and verify source digest pages are surfaced.
- Ask noisy related-page questions and verify unrelated candidates are not sent
  as primary evidence.
