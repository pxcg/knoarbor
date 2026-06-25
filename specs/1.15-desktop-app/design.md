# 1.15 Desktop App Design

## Design Summary

KnoArbor Desktop is an Electron-hosted local application that manages the
existing KnoArbor Python service and renders the existing React console.
The long-term product shape is chat-first and desktop-first; the current web
console is a transition asset, not the permanent information architecture.

```text
Electron Main
  -> Desktop Service Manager
      -> bundled Python service or external dev server
  -> Window Manager
  -> Native Menu
  -> Preload IPC Bridge
  -> Desktop Logs / Diagnostics / Updater

Renderer
  -> existing React console
  -> existing local HTTP API

KnoArbor Python Core
  -> ingest / lint / query / chat / vault / model / report / index
```

The desktop app is a product shell and lifecycle host. The core workflow
contracts remain in Python and continue to serve CLI, API, web console, and
host-AI skill callers.

Product shape details live in [product-shape.md](product-shape.md).

## Owning Architecture Layer

Add a Desktop Surface layer to the architecture taxonomy:

| Layer | Owns | Must not own |
| --- | --- | --- |
| Desktop Surface | Electron main process, packaged web assets, Python service lifecycle, native menus, preload IPC, desktop logs, intranet updater, OS app-data path resolution. | Ingest/lint/query/chat decisions, semantic prompts, model gateway policy, vault mutation rules, source parsing, report rendering, or retrieval ranking. |

Desktop Surface sits beside CLI, API, Web UI, and skills as an entry/surface
layer. It may call stable services through HTTP or through a narrow internal
startup contract. It should not reimplement workflow policy.

## Directory Shape

First implementation should add a focused desktop package without migrating the
whole repository into a TypeScript monorepo:

```text
desktop/
  package.json
  electron.vite.config.ts
  src/
    main/
      index.ts
      config.ts
      service-manager.ts
      window-manager.ts
      ipc.ts
      menu.ts
      logs.ts
      updater.ts
    preload/
      index.ts
      types.ts
    renderer/
      index.html
  resources/
    web/
    service/
```

The existing `web/` directory remains the React source. Desktop build scripts
copy the production web build into `desktop/resources/web/` or directly into the
Electron packaged resources.

## Runtime Modes

### Managed Packaged Service

Production desktop builds use managed mode:

```text
Electron starts
  -> resolve app-data config path
  -> choose available loopback port
  -> spawn packaged KnoArbor service
  -> wait for /health
  -> load http://127.0.0.1:<port>/
```

The service process should be launched with a deterministic environment:

```text
KNOARBOR_CONFIG_PATH=<app-data>/config.yaml
KNOARBOR_DESKTOP=1
KNOARBOR_LOG_DIR=<app-data>/logs
KNOARBOR_STATE_DIR=<app-data>/state
```

The packaged service should be a lightweight Python core bundle. The preferred
first packaging path is PyInstaller or an equivalent standalone executable
because it keeps user installation simple. A later packaging path can use
python-build-standalone plus wheels if size and transparency become more
important.

### External Development Service

Development mode can point to an existing local service:

```text
KNOARBOR_DESKTOP_APP_SERVER_URL=http://127.0.0.1:8000
```

In external mode, Electron does not start or stop the service. It still exposes
diagnostics and native menus.

## Process Lifecycle

The Service Manager owns:

- command construction;
- environment construction;
- port selection;
- stdout/stderr capture;
- health polling;
- crash detection;
- graceful shutdown;
- forced kill after timeout;
- restart;
- service diagnostics.

Lifecycle states:

```text
idle
  -> starting
  -> healthy
  -> stopping
  -> stopped
  -> failed
```

Startup failure should include:

- executable path;
- config path;
- selected port;
- elapsed startup time;
- exit code or signal;
- last stdout/stderr lines;
- log file path;
- suggested recovery action.

## Renderer Boundary

The React renderer remains a browser app. It uses HTTP APIs for:

- chat;
- ingest;
- lint;
- query;
- pages;
- graph;
- reports;
- runs;
- settings;
- models;
- token ledgers.

Renderer code may use `window.knoarborDesktop` only for desktop-native
operations:

- read desktop environment;
- open logs folder;
- open vault folder;
- open config file location;
- request service restart;
- read desktop service state;
- receive desktop-level command events;
- trigger native update check;
- show native file/directory picker when needed.

The renderer must not receive Node.js integration or direct filesystem access.

## Preload IPC Contract

Preload exposes a small bridge:

```ts
type KnoArborDesktopBridge = {
  getEnvironment(): Promise<DesktopEnvironment>;
  getServiceState(): Promise<DesktopServiceState>;
  getDiagnostics(): Promise<DesktopDiagnostics>;
  restartService(): Promise<DesktopServiceState>;
  openLogs(): Promise<{ opened: boolean; path?: string }>;
  openVault(input?: { vaultId?: string; path?: string }): Promise<{ opened: boolean }>;
  openConfig(): Promise<{ opened: boolean; path?: string }>;
  selectDirectory(input?: { title?: string }): Promise<{ canceled: boolean; path?: string }>;
  checkForUpdates(): Promise<DesktopUpdateCheckResult>;
  onCommand(listener: (command: DesktopCommand) => void): () => void;
  onServiceStateChanged(listener: (state: DesktopServiceState) => void): () => void;
};
```

IPC handlers validate inputs in the main process. They should return structured
errors using desktop-specific error codes that can be mapped into the existing
KnoArbor error-code style.

## Data Directories

Desktop app data should not live inside the application bundle or repository.

Recommended defaults:

| Platform | Config / State Root | Default Vault Root |
| --- | --- | --- |
| macOS | `~/Library/Application Support/KnoArbor/` | `~/KnoArbor/vaults/` |
| Windows | `%APPDATA%\\KnoArbor\\` | `%USERPROFILE%\\KnoArbor\\vaults\\` |
| Linux | `~/.config/knoarbor/` and `~/.local/share/knoarbor/` | `~/KnoArbor/vaults/` |

Suggested app-data layout:

```text
KnoArbor/
  config.yaml
  .env
  logs/
    desktop.log
    service.log
  state/
    service.json
    updates.json
  cache/
  vaults/
    default/
```

User vaults can be outside this root. The desktop app stores profiles, not
copies, unless the user creates a new desktop-managed vault.

## Package Boundary

The desktop package should include:

- Electron runtime;
- Electron main/preload bundle;
- React UI production build;
- KnoArbor Python service executable or embedded Python runtime;
- KnoArbor wheel and lightweight Python dependencies;
- default config template;
- icons, license, notices, and update metadata.

The desktop package should exclude:

- `.git`;
- `web/node_modules`;
- development virtual environments;
- tests and notebooks;
- `tmp`;
- user `vaults`;
- runtime logs and reports created by local use;
- MinerU, Ollama, vLLM, local model weights, OCR/VLM model files.

Expected size:

```text
compressed installer: 150-250 MB
installed app:       300-500 MB
```

This estimate assumes the package contains only the lightweight KnoArbor core.
Including MinerU/VLM/local model files would move package size into the GB
range and is outside the main desktop package.

## Intranet Update Architecture

Use Electron's generic update-provider model with an internal static release
URL.

Example update root:

```text
http://intranet.example/knoarbor/releases/
  latest-mac.yml
  latest.yml
  KnoArbor-1.5.0-arm64.dmg
  KnoArbor-1.5.0-x64.exe
  KnoArbor-1.5.0.blockmap
  checksums.txt
```

Update flow:

```text
app start or user action
  -> check update manifest
  -> compare app version
  -> download update
  -> wait until no active run
  -> stop managed service
  -> quit and install
  -> restart app
  -> run post-update checks
```

Rules:

- Updates affect application files only.
- User config, vaults, logs, `.env`, and model settings remain in app-data.
- Active ingest/lint/chat runs block immediate installation.
- Schema migrations are explicit post-update steps and should create backup or
  rollback notes when they mutate config or vault metadata.
- The updater should support an intranet generic provider first. Public update
  channels are future work.

## Logging And Diagnostics

Desktop diagnostics should combine:

- Electron version;
- platform and architecture;
- app version;
- packaged service version;
- service command and port;
- config path;
- log paths;
- service state;
- last service health result;
- update source and last update check;
- active run summary from the HTTP API when available.

Logs:

- `desktop.log`: Electron lifecycle, IPC, updater, window events;
- `service.log`: Python service stdout/stderr;
- existing KnoArbor runtime logs remain under the configured vault or
  app-data state root.

The UI should provide a single "Open Logs" action.

## Native Menus

Initial menu commands:

- New Chat;
- Open Settings;
- Open Vault Folder;
- Open Logs;
- Restart Local Service;
- Check For Updates;
- Toggle Developer Tools;
- GitHub / Documentation.

Menu commands should emit renderer events through preload. Business actions
still use HTTP APIs.

## Security Boundary

- BrowserWindow uses `contextIsolation: true`.
- `nodeIntegration` remains false.
- External links open in the system browser.
- Local file access goes through validated IPC handlers.
- The desktop app binds managed services to `127.0.0.1`.
- API keys stay in `.env` or OS credential storage when introduced.
- Update packages should be signed before broad distribution.

## Rejected Alternatives

### Rewrite The Core In Node.js

Rejected because current Python core already owns ingest, lint, query, chat,
vault, model, report, and index behavior. Rewriting would destabilize the
project without enough product benefit.

### Use Electron IPC As The Main API

Rejected because CLI, web, skills, and external tools already depend on the
local HTTP API. IPC should cover native desktop capabilities only.

### Require Users To Install Python And uv

Rejected for the normal desktop product because it keeps terminal setup in the
user path. It remains acceptable for developer mode.

### Bundle MinerU And Local Models In The Main App

Rejected because package size and platform compatibility would dominate the
desktop release. Heavy services remain optional external integrations.

### Store User Vaults Inside The App Bundle

Rejected because app updates replace application files. User data belongs in
app-data or user-selected directories.
