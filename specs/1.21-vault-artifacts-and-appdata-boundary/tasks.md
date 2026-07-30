# Vault Artifacts And AppData Boundary Tasks

- [x] Capture product decision: default desktop vault remains under app data.
- [x] Capture product decision: generated chat images move to `artifacts/chat`.
- [x] Add `artifacts` helpers to `storage.vault_layout`.
- [x] Update desktop bootstrap to create canonical app data and vault
  directories without duplicate or deprecated directories.
- [x] Update wiki vault initialization to create `artifacts/chat` and
  `.knoarbor/tmp`.
- [x] Update chat generated image storage to write
  `artifacts/chat/<session-id>/images`.
- [x] Add generated image manifest writing and metadata tests.
- [x] Update `/vault-assets` resolution to allow `raw/derived/assets/**` and
  `artifacts/**` only.
- [x] Update chat/image rendering tests for new artifact paths.
- [x] Remove deprecated source layout references from bootstrap, tests, and docs:
  `raw/normalized`, `raw/assets`, `raw/sidecars`,
  `raw/derived/assets/images/generated/chat`.
- [x] Define global/all-vault chat storage boundary and update session store
  callers.
- [x] Update backup/recovery, architecture, contract, and branch-boundary docs.
- [ ] Add doctor or status diagnostics that report app data root, config path,
  logs root, state root, and vault roots separately.
- [ ] Remove provider URLs from generated-image manifests and Chat traces.
- [ ] Bind generated images to their owning Chat request and reconcile them on
  turn replacement, turn deletion, and session deletion.
- [ ] Make the platform-local product root, Electron profile/cache subroots, and
  `state/endpoint.json` the only fresh-install desktop layout.
- [ ] Add bounded service-log rotation.
- [ ] Replace name-based backup exclusions with canonical root-aware selection.
- [ ] Bound and sanitize generated source-attachment path segments for Windows.
