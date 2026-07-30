# Desktop-First Transition Requirements

## Purpose

KnoArbor is moving from a web-console-centered product shape to a desktop-first product. During this transition, the desktop app becomes the only official end-user surface. The React UI remains as the desktop renderer implementation, and the Python service remains the local business runtime.

This is a development-stage transition. We do not need to preserve the old web-product structure, public `/ui` product entry, or browser settings-write behavior once the replacement path is implemented and verified.

## Goals

1. Make the Electron desktop app the official product entry point.
2. Reframe the React UI as a desktop renderer, not an independent web console.
3. Keep Python as the single business runtime for chat, query, ingest, lint, runs, wiki, reports, and model operations.
4. Use Electron IPC only for desktop-native capabilities: local configuration, OS dialogs, local path operations, logs, app-data, update flow, and service lifecycle.
5. Remove Python package ownership of static UI assets after the desktop renderer loading path is self-contained.
6. Rename or remove `/ui/api/*` contracts that are not truly UI-specific.
7. Keep the renderer browser-sandboxed: no Node integration and no direct filesystem access.
8. Simplify documentation, release, and build flows around desktop packages.
9. Establish one current desktop persistence layout before the first supported
   release; unpublished endpoint and runtime-layout variants are removed rather
   than migrated.
10. Desktop shutdown must wait for its managed Python service to exit. Windows
    uninstall and replacement must stop a surviving managed service owned by
    the current installation before removing application files.
11. Interactive Windows uninstall defaults to preserving product data and lets
    the user explicitly remove the local product-data root. External vaults are
    never deleted by the installer.

## Non-Goals

1. We will not migrate chat, streaming, ingest, lint, query, runs, wiki content, reports, or model probing into Electron IPC.
2. We will not make Electron main a second backend or duplicate Python business logic in TypeScript.
3. We will not keep a polished standalone web product after desktop-first migration completes.
4. We will not maintain legacy `.env` model-key flows, old web-first settings save paths, or compatibility shims for removed web deployment patterns.
5. We will not move Python source ownership under `desktop/`.

## Product Requirements

1. README and release surfaces present desktop installation as the default path.
2. Desktop launches without asking users to open a browser URL.
3. Desktop settings and local filesystem operations remain usable even when the HTTP business service is restarting, when feasible.
4. Desktop diagnostics expose service command, config path, port, log path, recent output, health state, and recovery actions.
5. Browser/Web mode is allowed only as a developer fallback until removed by this spec.

## Architecture Requirements

1. Electron main/preload owns OS capabilities and must expose only narrow IPC methods.
2. React renderer must call a small desktop bridge for local capabilities and a service client for business APIs.
3. Python local service owns business behavior and long-running runtime state.
4. Local HTTP remains loopback-only and is treated as an internal desktop runtime API.
5. Any new IPC capability must be explicitly categorized as local configuration, OS/native, app lifecycle, or desktop diagnostics.
6. Any attempt to IPC-wrap business APIs requires a new SDD and must justify why HTTP cannot satisfy the requirement.
7. Electron profile state is rooted under product `state/`, Electron session
   caches are rooted under product `cache/`, and neither becomes an alternate
   application-data authority.

## Acceptance Criteria

1. No production desktop code path saves settings through browser `fetch('/config*')`.
2. No Electron IPC handler executes chat, query, ingest, lint, wiki, report, run, or model probe business workflows.
3. Python package data no longer includes the renderer dist once Electron resource loading is complete.
4. `/ui` and `/ui/api/*` are removed or renamed out of public/product documentation.
5. Renderer remains sandbox-compatible and imports no Electron or Node modules outside the desktop bridge boundary.
6. Desktop build and release workflows produce the primary user artifacts.
7. Tests cover IPC contracts, Python local service APIs, renderer build, and desktop packaging smoke paths.
8. Windows reinstall and version upgrade replace the existing installation
   under its stable GUID without requiring a separate manual uninstall.
9. Windows uninstall preserves application data by default, terminates only the
   managed service executable under the current installation directory, and
   leaves no process that blocks installation of the next version.
