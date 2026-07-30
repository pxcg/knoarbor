# 1.27 Deterministic Entity Identity Verification

## Required Checks

- exact canonical name reuse;
- validated alias reuse;
- unambiguous acronym reuse;
- conflicting alias rejection;
- source alias/evidence preservation after linking and publication;
- restart and registry rebuild equivalence;
- stable entity ID after canonical display-name change;
- claim entity-ID closure;
- relation endpoint-ID closure;
- unchanged-ingest identity idempotency;
- legacy name-only reference migration rejects ambiguity.

## Commands

```bash
uv run python -m unittest tests.test_entity_registry tests.test_knowledge_atoms tests.test_knowledge_atom_index tests.test_source_revisions
uv run python -m unittest discover -s tests
```
