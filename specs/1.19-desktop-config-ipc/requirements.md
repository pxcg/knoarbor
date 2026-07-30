# Requirements

## Functional Requirements

1. In the desktop app, settings reads and writes must not use browser HTTP when the desktop bridge is available.
2. Browser mode must continue to use the existing HTTP endpoints.
3. Desktop config IPC must return the same payload shapes as the HTTP endpoints.
4. Desktop config writes must reuse `UiConfigService` and must not duplicate YAML rendering logic in Electron main.
5. Model discovery and capability probing may continue to use HTTP. When an
   edited field has an in-flight prerequisite save, the check must await that
   existing IPC write rather than starting another config helper process.
6. Workflow, chat, query, ingest, lint, run cancellation, page content editing, and feedback endpoints remain HTTP APIs.
7. Every config mutation validates and renders the complete candidate before it
   replaces the active file.
8. Config replacement is atomic within the config directory and never exposes
   a partially written YAML document.

## Security and DLP Requirements

1. Desktop config persistence must not send `config.yaml` content through browser `fetch`.
2. Desktop config persistence must not use multipart or form-data.
3. IPC handlers must accept only structured JSON payloads and return structured JSON payloads.
4. IPC handlers must not expose arbitrary shell execution.
5. Desktop-created config, endpoint, and service-state files must be readable
   and writable only by the current user where the platform supports POSIX
   permissions.

## UX Requirements

1. Existing instant-save behavior for blur, checkbox, select, and provider
   removal must remain intact. Model checks consume that persisted state without
   repeating the save.
2. Save failures must surface through the existing notice UI.
3. Desktop settings must remain usable even if the local HTTP service is restarting, as long as the packaged Python command is available.
4. Removing a vault profile unregisters it from configuration only. It must not
   delete, empty, move, or otherwise mutate the selected directory.
