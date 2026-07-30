# Desktop-First Transition Verification

## Architecture Gates

- Electron IPC handler list contains only local configuration, OS/native, app lifecycle, diagnostics, update, or menu/window commands.
- Electron main does not execute chat, query, ingest, lint, wiki, report, run, or model-probe business workflows.
- Renderer imports no Electron or Node modules outside the desktop bridge.
- Python package data no longer includes renderer dist after static UI hosting removal.
- Production docs no longer instruct users to open `/ui` as the product entry.

## Test Gates

Run the appropriate subset after each implementation phase:

- `.venv/bin/python -m ruff check src tests scripts`
- `.venv/bin/python -m unittest tests.test_desktop_config_cli tests.test_core_config tests.test_doctor tests.test_model_probe tests.test_ui_api tests.test_image_generation tests.test_chat_agent tests.test_chat_tool_flows tests.test_wiki_index_storage`
- `npm --prefix renderer run build`
- `npm --prefix desktop run build`
- `npm --prefix desktop run test:smoke`
- desktop packaged smoke test on macOS and Windows release runners
- fresh-start tree assertion for product root, `state/electron`, `cache/`, and
  the single runtime endpoint
- desktop shutdown test proving quit is resumed only after the managed service
  stop promise settles
- Windows NSIS contract test proving uninstall targets the exact managed
  service path, defaults to data preservation, and scopes optional deletion to
  `$LOCALAPPDATA\KnoArbor`

## Manual Checks

- Desktop starts without requiring a browser URL.
- Settings save does not trigger browser HTTP config writes.
- Chat streaming still uses the Python service runtime and preserves streaming/final/error semantics.
- Ingest/lint run events and cancellation continue to share the existing Python runtime contract.
- Service failure UI exposes config path, service command, port, logs, recent output, and recovery actions.
- No packaged process writes `~/.knoarbor` or a top-level app-data
  `.knoarbor`.
- On Windows, install a newer build directly over a running older build; the
  registered installation is replaced without manual uninstall and user data
  remains unchanged.
- On Windows, uninstall a running build; no `knoar-service.exe` process from
  the removed installation remains. Verify both preservation (default) and
  explicit local-data deletion while an external vault remains unchanged.

## Release Gates

- GitHub Release lists desktop installers as primary artifacts.
- Source archive is available, but web build is not described as an end-user deployment artifact.
- Release notes identify desktop runtime changes and any removed web-product surfaces.
