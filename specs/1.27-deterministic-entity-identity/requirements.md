# 1.27 Deterministic Entity Identity Requirements

## Status

Accepted target contract for public convergence. Implementation remains
pending against the KnoArbor 2.3.1 baseline.

## Ownership

This spec owns the conversion from 1.26 source-local entity contributions to
vault-canonical entity identities. It does not own semantic extraction,
evidence construction, factual publication, or projection.

## Requirements

1. Source entity contributions remain immutable factual input to linking.
2. Each contribution preserves source name, validated aliases, evidence, and
   source identity.
3. Canonical linking never clears or overwrites contribution aliases.
4. Exact canonical name, validated explicit alias, and unambiguous acronym are
   the only automatic linking rules.
5. Ambiguous candidates remain separate and produce diagnostics.
6. Canonical entity IDs are stable across process restart and canonical display
   name changes.
7. Published claims reference canonical entity IDs.
8. Published relation endpoints reference canonical entity IDs.
9. Registry state is rebuildable from active factual contributions.
10. Linking reads existing knowledge only for identity resolution, never as
    factual context for model extraction.

## Acceptance Criteria

- Alias contributions survive link, publish, restart, and registry rebuild.
- Claim and relation references remain closed after linking.
- Ambiguous aliases never merge unrelated entities.
- Unchanged ingest does not create a new canonical entity.
- Removing derived indexes does not remove entity identity authority.
