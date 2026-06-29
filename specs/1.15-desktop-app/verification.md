# 1.15 Desktop App Verification

## Automated Checks

Initial spec-only check:

```bash
uv run python -m unittest discover tests
uv run ruff check src tests
```

After the desktop scaffold exists:

```bash
npm --prefix web run build
npm --prefix desktop run typecheck
npm --prefix desktop run build
```

After the service artifact path exists:

```bash
npm --prefix desktop run build:service
desktop/resources/service/knoar-service --help
```

When desktop tests exist:

```bash
npm --prefix desktop test
```

The final release gate should include a packaged-app smoke check before desktop
builds are promoted to release-blocking.

## Manual Checks

### First Launch

- Start the desktop app from a clean app-data directory.
- Verify the app creates default config/state/log directories.
- Verify the managed service starts on a loopback port.
- Verify the main window opens only after `/health` succeeds.
- Verify the console can call `/health`, `/models`, `/vaults`, and `/chat`
  through the local service.

### Packaged Service Artifact

- Build the PyInstaller-style service artifact with `npm --prefix desktop run
  build:service`.
- Run `desktop/resources/service/knoar-service --help`.
- Create a temporary config and vault using `knoar-service --config <tmp>
  first-run --vault <tmp-vault> --no-example`.
- Start `knoar-service --config <tmp> serve --host 127.0.0.1 --port <free-port>`.
- Verify `GET /health` returns `status: ok`.
- Remove the temporary config and vault after the smoke check.

### Existing Vault

- Select an existing vault.
- Restart the app.
- Verify the selected vault profile persists.
- Verify the app does not copy or mutate the vault during selection.

### Service Failure

- Start the app with an intentionally invalid service executable or config.
- Verify the failure page shows:
  - startup command;
  - selected port;
  - config path;
  - exit code or signal;
  - recent stdout/stderr;
  - log path;
  - retry action.

### External Development Server

- Start a normal `knoar serve` service manually.
- Launch desktop with `KNOARBOR_DESKTOP_APP_SERVER_URL`.
- Verify Electron does not start a managed service.
- Verify the window loads the external URL.
- Verify service restart is unavailable or clearly marked external.

### Preload Security

- Verify `window.knoarborDesktop` exists in desktop mode.
- Verify Node globals are not available in the renderer.
- Verify local file opening goes through IPC and validated paths.
- Verify external links open in the system browser.

### Knowledge Base Settings

- Open Settings in the installed app.
- Click "New knowledge base" and verify the native operating-system directory
  picker opens.
- Cancel the picker and verify no new profile row appears.
- Select a directory and verify the profile row uses the selected directory
  name and path.
- Verify the settings UI does not expose the internal vault id.
- Verify "Open folder" opens the selected directory through IPC.
- Save settings, restart the desktop app, and verify `/ui/api/config` reports
  the desktop app-data config path rather than a temporary config file.

### Logs And Diagnostics

- Open logs from the app menu.
- Verify `desktop.log` and `service.log` exist.
- Verify diagnostics include Electron version, app version, platform, service
  state, service port, config path, and log paths.

### Intranet Update

- Point the app to a test generic update root.
- Verify no-update state is shown when current version is latest.
- Publish a newer test package manifest.
- Verify update detection, download state, and install prompt.
- Start a long-running run and verify install is blocked until the run ends or
  is cancelled.
- Verify user config and vault files remain outside app package updates.

## Package Size Checks

Record for each release candidate:

- compressed installer size;
- installed application size;
- packaged Python service size;
- packaged web resource size;
- whether optional heavy services are excluded.

Expected first target:

```text
compressed installer: 150-250 MB
installed app:       300-500 MB
service artifact:    10-40 MB
```

If the package exceeds this range, inspect whether development dependencies,
tests, runtime vaults, logs, `node_modules`, MinerU, local models, or cache
directories entered the package.

## Platform Matrix

| Platform | Required before public desktop release | Notes |
| --- | --- | --- |
| macOS arm64 | Yes | Primary development platform. |
| macOS x64 | Later | Can follow after arm64 package is stable. |
| Windows x64 | Yes before broad desktop release | Path, certificate, and service spawning checks are required. |
| Linux x64 | Later | Useful for labs, not first packaged target. |

## Release Readiness

The desktop app is release-ready when:

- managed and external modes work;
- packaged service starts without a developer checkout;
- app-data directories are stable;
- logs and diagnostics are visible;
- update source configuration is documented;
- active-run update blocking works;
- no user vault, `.env`, or API key is bundled into the app;
- desktop-specific behavior is documented in public docs;
- existing CLI/API/skill workflows remain unaffected.
