# Desktop-First Transition Tasks

- [x] Run independent supporting and challenging architecture reviews.
- [x] Record desktop-first requirements, design boundaries, and rejected alternatives.
- [ ] Update public docs to present desktop as the primary product entry.
- [ ] Mark browser/Web mode as development-only in docs and code comments.
- [ ] Add IPC allowlist guidance to desktop architecture documentation.
- [ ] Remove production settings HTTP writes from desktop paths.
- [ ] Move renderer loading fully to Electron resources.
- [ ] Remove `src/knoarbor/ui/dist` from Python package data.
- [ ] Retire FastAPI static UI routes in desktop production mode.
- [ ] Rename remaining `/ui/api/*` endpoints to business-local endpoint names.
- [ ] Rename `web/` to `renderer/` or another accepted desktop-renderer name.
- [ ] Update build scripts and CI after renderer rename.
- [ ] Add desktop startup and diagnostics smoke tests.
- [ ] Add a release checklist gate that verifies desktop artifacts are primary.
