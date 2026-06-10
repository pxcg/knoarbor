# Vault Workspaces Requirements

## Goal

Treat each configured KnoArbor vault as a named knowledge-base workspace instead
of a raw filesystem path. Users, APIs, CLI commands, and skills should select
vaults by stable IDs whenever a `config.yaml` is available.

## Scenarios

- A user lists configured knowledge bases before running query, ingest, or lint.
- A host-AI skill discovers vault IDs and asks the user which vault to use.
- A query can search one vault, selected vaults, or all configured vaults.
- A write workflow targets exactly one vault per run.
- Reports and run records carry vault identity so results can be explained
  without exposing only local paths.

## Acceptance Criteria

- `GET /vaults` returns configured vault profiles with ID, name, path, active
  state, and availability.
- `knoar vaults` and the portable skill helper can list the same registry.
- Public docs describe `vault_id` as the preferred integration selector and
  `vault_path` as the explicit one-off path selector.
- Existing single-vault configs continue to materialize a default vault profile.
- Tests cover API, CLI, and skill-level vault listing.
