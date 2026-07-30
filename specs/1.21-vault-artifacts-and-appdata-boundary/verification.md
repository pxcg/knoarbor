# Vault Artifacts And AppData Boundary Verification

## Automated Checks

Run:

```bash
uv run python -m unittest \
  tests.test_wiki_init \
  tests.test_ui_api \
  tests.test_image_generation \
  tests.test_chat_tool_flows
```

After implementation, add or update tests to verify:

- fresh vault initialization creates `artifacts/chat` and `.knoarbor/tmp`;
- fresh vault initialization does not create deprecated old layout directories;
- generated chat images are stored under `artifacts/chat/<session-id>/images`;
- generated image manifests contain provider, model, prompt, digest, MIME type,
  request identity, and stored relative path, but no provider URL;
- generated-image completion fails when provider bytes cannot be retained;
- deleting or regenerating a turn removes only that turn's generated images;
- deleting a session removes its complete generated artifact directory;
- source attachment images remain under `raw/derived/assets/images`;
- `/vault-assets` serves `raw/derived/assets/**` and `artifacts/**`;
- `/vault-assets` rejects `.knoarbor/**`, `raw/inbox/**`, absolute paths, and
  traversal attempts.

## Manual Checks

- On a fresh desktop install, inspect the app data root and confirm all default
  product files remain under that root.
- Confirm app data `logs`, `state`, `cache`, and `tmp` are separate from
  `vaults/default`.
- Generate an image in chat and confirm the rendered Markdown image loads after
  restarting the app.
- Process a document with image attachments and confirm attachment evidence still
  renders in chat/wiki views.
- Copy `vaults/default` to a temporary location and confirm wiki pages,
  attachments, artifacts, reports, and optional chat history remain readable.
- Delete rebuildable `.knoarbor/index` in a copied vault and confirm index
  rebuild restores search visibility.

## Release Gate

- Documentation states the backup boundary and the disposable runtime/cache
  boundary.
- Source packages exclude generated build outputs but do not exclude canonical
  source files or spec files.
- No tests or release scripts operate on the user's real app data root by
  default.
- Backup round-trip preserves durable vault directories named `Cache`, `logs`,
  and `tmp`.
- Generated attachment filenames remain within the declared segment bound and
  avoid Windows-reserved names.
- Repeated service output produces bounded rotated log files.

