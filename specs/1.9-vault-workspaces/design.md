# Vault Workspaces Design

## Ownership

- Config layer owns `vaults.profiles` and the active default vault.
- Vault registry service owns read-only vault listing.
- API, CLI, UI, and skills treat `vault_id` as the preferred stable selector.
- Storage, retrieval, audit, queue, and runtime layers still operate on resolved
  `Path` values after selection.

## Public Contract

`GET /vaults` returns:

```json
{
  "schema_version": "vaults.v1",
  "config_path": "/path/to/config.yaml",
  "default_vault_id": "personal",
  "vaults": [
    {
      "id": "personal",
      "name": "Personal Knowledge Base",
      "path": "/path/to/wiki",
      "active": true,
      "exists": true
    }
  ]
}
```

The CLI exposes the same contract through:

```bash
knoar vaults
knoar vaults list
```

The portable skill helper exposes:

```bash
python3 scripts/knoarbor.py vaults list
```

## Selector Rules

- Read operations can use `vault_id`, `vault_path`, `all_vaults`, or
  `vault_ids`, depending on endpoint support.
- Write operations use one selected vault per request.
- `vault_id` requires a config context. If no explicit `config_path` is
  provided, runtime discovery supplies it.
- `vault_path` remains available for temporary automation and tests.

## Internal Boundary

After selection, lower layers receive a resolved path. They do not inspect
`vaults.profiles` or interpret user-facing vault names.

This keeps workspace identity in the integration/config layer and keeps storage
code simple and deterministic.

## Renderer Boundary

The renderer separates:

- a concrete workspace vault used by Wiki, graph, ingest, lint, reports,
  tokens, and other single-vault pages;
- a Chat retrieval scope, which may be a concrete vault or the virtual
  all-vault scope;
- Query's explicit single/all-vault search scope.

Page-local switchers are direct consumers of the shared concrete workspace
selection. They are not independent persisted authorities. Cross-page targets
carry `vault_id` so the destination switcher, cache key, and API selector agree.
Reports consume only the concrete workspace selection and expose no nested
all-vault selector. Report and run links must carry their originating vault;
the renderer does not repair a missing identity by substituting the currently
selected workspace.
