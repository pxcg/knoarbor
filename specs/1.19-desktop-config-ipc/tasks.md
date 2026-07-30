# Tasks

- [x] Document the desktop config IPC boundary.
- [x] Add a `desktop-config` Python CLI command backed by `UiConfigService`.
- [x] Add Electron IPC handlers for config operations.
- [x] Extend the preload bridge and renderer desktop bridge types.
- [x] Route config client functions through IPC in desktop mode with HTTP fallback.
- [x] Add focused tests for the local config CLI command.
- [x] Run Python tests, web build, and desktop build.
- [x] Remove the desktop arbitrary-directory deletion IPC and make vault removal configuration-only.
- [x] Add renderer coverage proving vault removal leaves the selected directory untouched.
- [x] Make raw, form, and capability config writes validate then atomically
  replace a private config file.
- [x] Add fault-oriented tests proving an invalid candidate does not change the
  active config.
