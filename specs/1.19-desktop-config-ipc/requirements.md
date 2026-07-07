# Requirements

## Functional Requirements

1. In the desktop app, settings reads and writes must not use browser HTTP when the desktop bridge is available.
2. Browser mode must continue to use the existing HTTP endpoints.
3. Desktop config IPC must return the same payload shapes as the HTTP endpoints.
4. Desktop config writes must reuse `UiConfigService` and must not duplicate YAML rendering logic in Electron main.
5. Model discovery and capability probing may continue to use HTTP, but their prerequisite config save must use IPC in desktop mode.
6. Workflow, chat, query, ingest, lint, run cancellation, page content editing, and feedback endpoints remain HTTP APIs.

## Security and DLP Requirements

1. Desktop config persistence must not send `config.yaml` content through browser `fetch`.
2. Desktop config persistence must not use multipart or form-data.
3. IPC handlers must accept only structured JSON payloads and return structured JSON payloads.
4. IPC handlers must not expose arbitrary shell execution.

## UX Requirements

1. Existing instant-save behavior for blur, checkbox, select, provider removal, and model checks must remain intact.
2. Save failures must surface through the existing notice UI.
3. Desktop settings must remain usable even if the local HTTP service is restarting, as long as the packaged Python command is available.
