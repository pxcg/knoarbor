# 1.15 Desktop Product Shape

## Decision Summary

KnoArbor Desktop is a chat-first desktop knowledge application. It is not a
browser wrapper around the existing management console.

Confirmed product decisions:

- The desktop home screen is Chat.
- The layout is desktop-first.
- Settings open as a native-menu-triggered in-app modal panel.
- Knowledge-base paths use the system directory picker.
- Model configuration is a first-class desktop setting.
- MinerU, Ollama, vLLM, and other external services do not get a separate
  always-visible status panel in the first desktop shape.
- Update status and update actions live in Settings.
- API docs remain accessible, but open in the system browser.
- Desktop UI design is the primary future surface.
- The current Web Console is a transition asset; long-term web-first frontend
  development is not the priority.
- First launch requires only model setup in Settings before normal ingest and
  chat use.

## Product Position

The desktop app should feel like a local AI knowledge workspace:

```text
open app
  -> ask questions
  -> compile documents or selected conversations when needed
  -> inspect generated pages and reports when useful
  -> maintain knowledge base from the same local app
```

The user should not feel they are operating a service dashboard. Runtime,
reports, diagnostics, and settings remain available, but they support the main
chat and knowledge workflow instead of competing with it.

## Information Architecture

### Primary Surface

```text
Chat
  - conversation list
  - active conversation
  - model selector
  - vault selector
  - source citations
  - compile this conversation action
```

Chat is the home route and the default window content after service startup.

### Secondary Surfaces

Secondary surfaces should be reachable from the app shell, command menu, or
contextual actions:

```text
Knowledge Base
  - pages
  - source digests
  - attachments
  - graph view

Ingest
  - import documents
  - import folders
  - import selected chat/session excerpts
  - show current run result

Runs And Reports
  - active workflow status
  - recent runs
  - report details
  - generated page links
  - lint diffs

Settings
  - models
  - vaults
  - source paths
  - document processing endpoint
  - updates
  - diagnostics
```

The current web console pages may be reused during transition, but the desktop
product should consolidate pages that read like an operations dashboard.

## App Shell

Desktop layout should use:

- a narrow conversation/sidebar area for chat sessions and primary navigation;
- a main chat/workspace area;
- optional right-side detail drawer for citations, page preview, run result, or
  settings sub-detail;
- no browser-like top URL bar;
- no dashboard-first overview screen.

The app should remain usable at common desktop sizes:

- minimum: 1080 x 720;
- default: about 1360 x 900;
- wide monitor: content stretches through layout regions, not by making text
  lines too long.

## First Launch

First launch flow:

```text
app starts
  -> managed service starts
  -> Chat screen opens
  -> if no usable model provider:
       show model setup prompt
       open Settings modal to Models
  -> user configures model
  -> user can chat, ingest, or import knowledge
```

First launch should not require a separate setup wizard unless model setup or
vault creation fails.

Default vault behavior:

- create or select a desktop-managed default vault path;
- expose vault selection in the chat header;
- allow changing or adding vaults in Settings;
- use system folder picker for path selection.

## Settings Modal

Settings should be an in-app modal panel triggered by:

- native menu: Settings;
- keyboard shortcut: `Cmd/Ctrl+,`;
- settings icon/button in the app shell.

Settings tabs:

```text
Models
  - provider list
  - add provider
  - discover models
  - probe selected model
  - default chat model
  - default workflow model

Knowledge Bases
  - vault profiles
  - default vault
  - add/select directory
  - open vault folder

Sources
  - Markdown paths
  - chat record paths
  - selected excerpt input
  - document originals path

Document Processing
  - MinerU endpoint
  - backend options
  - image/attachment extraction options

Updates
  - current app version
  - update channel/source
  - check for updates
  - last update status

Diagnostics
  - service state
  - config path
  - log path
  - open logs
  - open API docs in browser
```

The settings modal should be the normal place for model setup. External service
availability can be shown inside relevant settings sections, not as a separate
status dashboard.

## Folder Selection

The desktop app should use the system directory picker for:

- adding a vault path;
- choosing Markdown notes directory;
- choosing chat record directories when custom;
- choosing document originals directory;
- choosing MinerU output directory only if exposed as advanced setting.

Renderer code must request directory selection through preload IPC. It should
not access Node.js or filesystem APIs directly.

## Model Configuration

Model setup is first-class because first launch depends on it.

The model settings experience should support:

- OpenAI-compatible providers;
- DeepSeek;
- Ollama;
- vLLM;
- custom provider;
- provider discovery when supported;
- model probe;
- persistent capability status after successful probe;
- TLS certificate path / verify option where relevant.

The desktop app should let users pick the active chat model from the chat
header. Workflow defaults stay in Settings.

## API Docs

API docs remain useful for developers and automation users, but they are not a
primary desktop page.

Behavior:

- "API Docs" opens `http://127.0.0.1:<port>/docs` in the system browser.
- If the service is unavailable, show diagnostics first.
- The desktop UI should not embed Swagger as a core workspace.

## External Services

External services include MinerU, Ollama, vLLM, and remote model endpoints.

First desktop shape:

- configure them in Settings;
- show inline availability/probe result inside Settings;
- do not create a permanent external-service status page;
- do not bundle their models or runtimes in the main app.

## Transition From Web Console

The existing React web console is a reusable asset, not the final desktop IA.

Transition strategy:

1. Desktop shell loads current UI to prove lifecycle and packaging.
2. Chat becomes the default route and visual priority.
3. Settings moves to modal/product shape.
4. Operational pages are merged or demoted behind contextual actions.
5. Web console support can remain for developers while desktop becomes the
   normal user surface.

## Design Guardrails

- Chat-first, not dashboard-first.
- Settings are deep but not always visible.
- Runtime information is contextual, not the homepage.
- Model setup should be obvious on first launch.
- Ingest results should be inspectable immediately after a run.
- Lint diffs should be viewable from run/report context.
- API and diagnostics remain accessible without dominating the product.
- Heavy optional services stay outside the main app package.

## Implementation Impact

This product shape changes the priority of the remaining desktop tasks:

- P3 should focus on secure window/preload/menu foundation and settings modal
  trigger, not a broad native menu feature set.
- P4 should prioritize app-data config bootstrap and model setup.
- P5 should package the Python service only after the desktop shell can run the
  chat-first UI with an external/dev service.
- P6 updater UI belongs in Settings.
- Existing web pages should be reused only where they match desktop IA.

