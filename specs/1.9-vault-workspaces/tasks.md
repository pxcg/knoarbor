# Vault Workspaces Tasks

- [x] Add a typed vault registry response schema.
- [x] Add a read-only vault registry service.
- [x] Expose `GET /vaults` as a stable public API.
- [x] Add `knoar vaults` CLI command.
- [x] Add portable skill helper support for `vaults list`.
- [x] Document `vault_id` as the preferred selector.
- [x] Cover API, CLI, and skill helper behavior with tests.
- [x] Continue UI consolidation so every page uses the selected vault ID as the
      primary workspace selector.
- [x] Separate the concrete renderer workspace vault from Chat's all-vault
      retrieval scope.
- [x] Expose one shared page-local vault switcher on every vault-scoped page.
- [x] Verify cross-page destination identities include the vault ID.
- [x] Remove Reports' nested vault filter and reject identity-less report/run
      citation navigation.
