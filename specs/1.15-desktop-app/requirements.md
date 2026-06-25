# 1.15 Desktop App Requirements

## Problem

KnoArbor currently ships as a Python package with a local FastAPI service and a
bundled React console. This is a good developer and power-user shape, but it is
not yet a full desktop product:

- users still need to start a terminal service before opening the console;
- local service logs, ports, and failures are visible only to users who watch a
  terminal;
- Python and `uv` setup remain part of the mental model;
- intranet update, local data location, and app lifecycle are not productized;
- Windows and macOS users expect a double-click application, native menus, and
  application-data directories instead of a repository checkout.

The desktop direction should improve product experience without rewriting the
knowledge engine. KnoArbor's core value lives in the Python ingest, lint, query,
chat, vault, model, report, and index layers. Electron should host and manage
that core, not replace it.

## Goals

- Provide a first-class Electron desktop application for KnoArbor.
- Make Chat the desktop home surface.
- Prefer a desktop-first UI layout over a dashboard-style web console layout.
- Keep Python/FastAPI as the core runtime and source of truth for workflows.
- Reuse the current React console instead of building a second UI.
- Start, stop, restart, and observe the local KnoArbor service from the desktop
  app.
- Package the lightweight Python core and dependencies with the desktop app for
  normal users.
- Keep heavy optional services, models, and document parsers external:
  MinerU, Ollama, vLLM, local LLM weights, and VLM/OCR model files.
- Use OS application-data directories for user config, vaults, logs, runtime
  state, and updates.
- Support intranet release updates through a generic static update source.
- Preserve CLI, API, and host-AI skill use for developers and automation.
- Keep desktop-specific native abilities behind a narrow preload bridge.
- Treat the existing Web Console as a transition surface while desktop UI
  becomes the future primary product surface.

## Non-Goals

- Do not migrate KnoArbor's core engine from Python to Node.js.
- Do not keep the current dashboard/management-console layout as the long-term
  desktop product shape.
- Do not put MinerU, vLLM, Ollama, or large model files into the main desktop
  package.
- Do not require the desktop renderer to access Node.js directly.
- Do not fork the React UI into a separate product surface unless a desktop-only
  interaction requires a thin adapter.
- Do not make auto-update mutate user vault content, `.env`, or API keys.
- Do not replace the public HTTP API with Electron IPC.
- Do not require an online public update server for intranet deployments.

## User Scenarios

### First Launch

When a user opens KnoArbor Desktop for the first time, the app creates or
discovers a desktop config directory, starts the bundled local service on an
available loopback port, waits for `/health`, and opens the console.

### Existing Vault

When a user already has a vault, the app lets them select that vault path and
stores the profile in the desktop config. The vault remains ordinary local
files that can be backed up, inspected, and opened in other tools.

### Service Failure

When the Python service cannot start, the desktop app shows a clear failure
screen with the command, exit code, log path, and suggested next action. The
user can open logs or retry startup without using a terminal.

### Intranet Update

When the app is deployed inside a lab or company network, the desktop updater
checks a configured internal static update URL, downloads a newer signed
desktop package, stops the managed service, and installs the update after user
confirmation.

### Developer Mode

When a contributor works on KnoArbor, the desktop app can load an external
development server instead of starting a packaged service. This keeps frontend,
API, and Electron development loops short.

### Optional External Services

When a user configures MinerU, Ollama, vLLM, or a remote model endpoint, the
desktop app stores connection settings and probes availability. Those services
remain external processes or remote endpoints.

## Acceptance Criteria

- A desktop app spec defines requirements, design, tasks, and verification.
- The desktop app has a clear owning architecture layer and does not duplicate
  ingest, lint, query, chat, vault, model, report, or index logic.
- The desktop service manager can run in two modes:
  - managed packaged service;
  - external development service URL.
- The packaged service startup contract includes command, environment, config
  path, port selection, health wait, logs, and shutdown.
- The renderer calls existing HTTP APIs for KnoArbor business workflows.
- Preload IPC exposes only native desktop abilities such as diagnostics, log
  opening, native dialogs, and service lifecycle commands.
- Desktop data directories are defined for macOS, Windows, and Linux.
- The package boundary excludes dev dependencies, repository history, tests,
  runtime vault data, temporary files, and heavy model services.
- Intranet update architecture is documented with manifest, package, signature,
  rollback, and active-run handling.
- Verification covers service startup, failure display, log access, packaged UI
  loading, external-server mode, and update-source configuration.
