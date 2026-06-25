# 1.15 Desktop App Tasks

## P0 Spec And Architecture Boundary

- [x] Create desktop app SDD requirements, design, tasks, and verification.
- [x] Define Electron as a desktop surface layer rather than a core workflow
  layer.
- [x] Freeze Python core as the workflow runtime.
- [x] Freeze Electron/Node responsibilities: service lifecycle, native window,
  native menu, IPC bridge, logs, and updater.
- [x] Freeze package boundary: lightweight core bundled, heavy model services
  external.
- [x] Freeze desktop product shape as chat-first, desktop-first, settings-modal
  driven, and future-primary over the old web console.

## P1 Desktop Project Scaffold

- [x] Add `desktop/package.json`.
- [x] Add `desktop/electron.vite.config.ts`.
- [x] Add main, preload, and renderer entry points.
- [x] Add scripts for:
  - `desktop:dev`;
  - `desktop:build`;
  - `desktop:typecheck`;
  - `desktop:prepare-web`.
- [x] Copy or prepare the existing `web/` production build into desktop
  resources.
- [x] Keep desktop dependencies isolated from Python runtime dependencies.

## P2 Managed Service Runtime

- [x] Implement `service-manager.ts`.
- [ ] Support managed packaged service mode.
- [x] Support external development server mode.
- [x] Add automatic loopback port selection.
- [x] Wait for `/health` before showing the main window.
- [x] Capture service stdout/stderr into `service.log`.
- [x] Add graceful shutdown and forced kill timeout.
- [x] Add restart operation.
- [x] Add structured failure state for startup errors.

## P3 Window, Menu, And Preload Bridge

- [x] Implement `window-manager.ts`.
- [x] Use secure BrowserWindow defaults:
  - `contextIsolation: true`;
  - `nodeIntegration: false`;
  - controlled preload script.
- [x] Implement a minimal native menu for New Chat, Settings, Open Logs, API
  Docs, and Developer Tools.
- [x] Implement preload bridge types.
- [x] Implement IPC handlers for safe desktop operations.
- [x] Add renderer detection for desktop mode without changing HTTP workflow
  behavior.
- [x] Add settings modal trigger contract; detailed settings content belongs to
  P4 and product UI work.

## P4 Desktop App-Data And Config Bootstrap

- [x] Resolve app-data paths for macOS, Windows, and Linux.
- [x] Create default desktop config when missing.
- [x] Create default desktop vault root when requested by first launch.
- [ ] Keep user-selected vaults as profiles rather than copies.
- [ ] Keep `.env` and API keys outside packaged resources.
- [x] Add app-data diagnostics to UI settings or diagnostics.
- [x] Add system directory picker IPC for vault and source paths.
- [ ] Add lightweight first-launch settings reminder when model setup is
  missing; no forced onboarding until product UI stabilizes.
- [ ] Move update status and update check into Settings.

## P5 Python Service Packaging

- [ ] Decide first packaging implementation:
  - PyInstaller service executable; or
  - standalone Python runtime plus wheel install.
- [ ] Build a local service artifact.
- [ ] Verify the artifact can run `knoar serve` without a developer `.venv`.
- [ ] Copy service artifact into desktop resources.
- [ ] Exclude dev dependencies, tests, notebooks, `tmp`, `vaults`, `.git`, and
  `web/node_modules`.
- [ ] Record package size for macOS and Windows builds.

## P6 Intranet Update

- [ ] Add desktop update config for generic provider.
- [ ] Add manual "Check For Updates" command.
- [ ] Add update diagnostics.
- [ ] Block install while active runs are present.
- [ ] Stop the managed service before install.
- [ ] Document internal static release root layout.
- [ ] Add rollback notes and user-data safety rules.

## P7 Verification And Release Gates

- [ ] Add desktop typecheck.
- [ ] Add main-process unit tests for service manager state transitions.
- [ ] Add preload bridge type test or compile check.
- [ ] Add packaged-web smoke check.
- [ ] Add Playwright/Electron smoke for first window load.
- [ ] Add manual verification checklist for macOS.
- [ ] Add manual verification checklist for Windows before public desktop
  release.
- [ ] Update release checklist once desktop builds become release-blocking.

## P8 Public Docs

- [ ] Add desktop installation section after first usable build exists.
- [ ] Add desktop troubleshooting section.
- [ ] Add desktop update instructions for intranet deployments.
- [ ] Add desktop screenshots after UI stabilizes.
- [ ] Update README when desktop becomes the recommended normal-user entry.
