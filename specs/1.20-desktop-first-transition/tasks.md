# Desktop-First Transition Tasks

- [x] Run independent supporting and challenging architecture reviews.
- [x] Record desktop-first requirements, design boundaries, and rejected alternatives.
- [x] Update public docs to present desktop as the primary product entry.
- [x] Mark browser/Web mode as development-only in docs and code comments.
- [x] Add IPC allowlist guidance to desktop architecture documentation.
- [x] Remove production settings HTTP writes from desktop paths.
- [x] Move renderer loading fully to Electron resources.
- [x] Remove `src/knoarbor/ui/dist` from Python package data.
- [x] Retire FastAPI static UI routes in desktop production mode.
- [x] Rename remaining `/ui/api/*` endpoints to business-local endpoint names.
- [x] Rename `web/` to `renderer/`.
- [x] Update build scripts and CI after renderer rename.
- [x] Add desktop startup and diagnostics smoke tests.
- [x] Add a release checklist gate that verifies desktop artifacts are primary.
- [x] Resolve the product root independently from Electron profile and cache
  paths.
- [x] Pass the single canonical runtime state directory to the Python service
  and remove unpublished endpoint compatibility paths.
- [x] Make desktop quit await managed-service shutdown and add an exact-path
  Windows uninstall cleanup boundary.
- [x] Preserve local data by default while offering explicit local-data removal
  during interactive Windows uninstall.
