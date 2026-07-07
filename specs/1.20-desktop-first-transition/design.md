# Desktop-First Transition Design

## Reviewed Positions

Two independent architecture reviews were considered:

- The desktop-first supporting review recommended a three-layer architecture: Electron product shell, React desktop renderer, and Python local business engine. It also recommended removing Python-hosted static UI, retiring `/ui/api/*`, and renaming `web/`.
- The challenge review warned against confusing desktop-first with IPC-first. It recommended keeping chat, query, ingest, lint, runs, wiki, reports, and model operations on the Python service API, while limiting IPC to native desktop capabilities.

This design adopts both positions: KnoArbor becomes desktop-first, but the Python service remains the only business runtime.

## Target Architecture

```text
Electron desktop shell
  desktop/src/main
  desktop/src/preload
  - windows, menus, app lifecycle
  - service lifecycle and diagnostics
  - local config, app-data, file dialogs, path opening
  - narrow IPC only

React desktop renderer
  future: renderer/ or app-ui/
  current: web/
  - UI state, views, interaction
  - desktop bridge for local capabilities
  - service client for business APIs
  - no Node or filesystem access

Python local business runtime
  src/knoarbor
  - chat, query, ingest, lint, runs, wiki, reports
  - model gateway and model discovery
  - vault storage, indexes, ledgers, reports
  - loopback-only HTTP runtime API
```

## Boundary Rules

### IPC Allowlist

IPC may own:

- config read/write and config diagnostics;
- vault profile local configuration;
- file and directory pickers;
- opening local paths and logs;
- protected local deletion or cleanup actions;
- service start, stop, restart, status, and recent output;
- desktop diagnostics bundle;
- app update and release-channel controls;
- menu and window commands;
- app-data migration and local bootstrap;
- future OS credential-store integration.

### HTTP Business API Ownership

HTTP remains the owner for:

- `/chat` and `/chat/stream`;
- chat sessions, retry, close, delete, and chat-ingest;
- `/query` and query feedback;
- `/ingest`, source ingest, file/folder/excerpt/recovery ingest;
- `/lint`, runs, run events, run cancel, rerun;
- wiki pages, page content, relations, reports, graph, tokens;
- source catalog and source diagnostics;
- model provider listing, model discovery, and capability probing;
- health and runtime readiness.

Electron main must not call Python CLI or service classes to perform those business operations. It should manage the service and let the renderer talk to the local service API.

## Directory Plan

### Phase 1: Reframe Without Moving

Keep current directories while changing ownership language:

```text
desktop/      product shell and native bridge
web/          desktop renderer implementation, not a web product
src/knoarbor/ Python local runtime
```

The immediate goal is to avoid large path churn while specs, docs, and build scripts converge on desktop-first language.

### Phase 2: Remove Python Static UI Hosting

Remove Python package ownership of renderer dist:

- delete `src/knoarbor/ui/dist` from package data;
- stop serving `/`, `/ui`, and `/ui/assets` from FastAPI in packaged desktop mode;
- load renderer from Electron resources;
- keep local service API available under business endpoints only.

### Phase 3: Rename Renderer

Once Python static UI hosting is gone, rename `web/` to a desktop-oriented name. Preferred target:

```text
renderer/
```

Alternative acceptable names:

```text
app-ui/
desktop-renderer/
```

Do not move React code under `desktop/src/main` or mix Electron imports into view components.

### Phase 4: Retire `/ui/api/*`

Rename the remaining `/ui/api/*` endpoints into business-local endpoints:

- `/ui/api/status` -> `/status` or `/vaults/status`;
- `/ui/api/graph` -> `/graph`;
- `/ui/api/tokens` -> `/tokens`;
- `/ui/api/vault-assets/*` -> `/assets/*` or `/vault-assets/*`;
- config HTTP endpoints removed from desktop production path after IPC coverage is complete.

## Runtime Flow

### Desktop Startup

```text
Electron main
  -> resolve app-data and config path
  -> bootstrap config/vault layout if missing
  -> start Python local service on 127.0.0.1
  -> load renderer from packaged resources
  -> expose service endpoint and desktop bridge through preload
```

### Settings Save

```text
renderer settings state
  -> desktop bridge
  -> Electron IPC
  -> local Python config helper
  -> UiConfigService
  -> config.yaml
```

### Business Operation

```text
renderer action
  -> service API client
  -> loopback HTTP
  -> Python ApplicationServices
  -> vault/runtime/model services
```

## Rejected Alternatives

### Move All Business APIs To IPC

Rejected. It creates a second backend in Electron main, duplicates contracts, breaks long-running runtime semantics, and would require reimplementing streaming, cancellation, queues, and reporting protocols.

### Keep Web Console As A First-Class Product

Rejected. The target product is local desktop. Keeping a polished standalone web product perpetuates DLP, browser permission, deployment, and documentation ambiguity.

### Move Python Core Under `desktop/`

Rejected. Python remains the local business runtime and CLI/API/skill substrate. Desktop packages may bundle Python artifacts, but source ownership stays under `src/knoarbor`.

### Let Renderer Use Node APIs Directly

Rejected. Renderer must remain browser-sandboxed. Native powers go through a narrow audited preload bridge.

## Documentation Impact

Public docs should stop leading with browser URLs. Desktop docs become primary:

- installation;
- first run;
- settings;
- logs and diagnostics;
- packaging and release;
- enterprise local runtime boundaries.

API docs remain developer/runtime docs, not product entry docs.
