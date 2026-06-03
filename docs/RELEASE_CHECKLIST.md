# Release Preflight Checklist

This checklist defines the release gate for KnoArbor. It is intentionally broader than a test command: a release should be usable from a clean clone, safe to publish, and understandable to a new user.

Use this document before every public tag. The automated scripts cover only part of the checklist; the remaining items require maintainer review.

## 1. Repository Boundary

Confirm that only source code, public documentation, and intentional static assets are tracked.

Required checks:

```bash
git status --short
git ls-files | rg '(^wiki/|^dist/|node_modules|\.venv|\.uv-cache|\.pytest_cache|egg-info|knoarbor_logo_asset_kit|\.obsidian)' || true
```

Expected result:

- `git status --short` is empty before tagging.
- Runtime vaults, local workflow exports, build artifacts, virtual environments, caches, and private design notes are not tracked.
- `src/knoarbor/ui/dist/` is allowed because it is the bundled console asset shipped with the Python package.

Runtime data isolation:

- Review scripts that reference `wiki`, `config.yaml`, `.env`, local source directories, or connector session paths.
- Release/test scripts may read `config.example.yaml`, but any writable config or vault must live under `mktemp -d`.
- Block the release if any automated gate writes to project-root `wiki/`, `config.yaml`, `.env`, or private connector source directories.
- The acceptable exception is a clean-clone smoke test that writes `wiki/` inside its temporary clone, never inside the maintainer's working tree.

## 2. Privacy And Secret Review

Confirm that the release contains no personal data, local private vaults, API keys, raw chat logs, or private workflow exports.

Required checks:

```bash
rg -n '/Users/|/home/|DEEPSEEK_API_KEY=|sk-[A-Za-z0-9_-]{12,}|api_key\s*:|apiKey\s*:' \
  README.md README.zh-CN.md docs src tests config.example.yaml .env.example .github pyproject.toml || true
```

Acceptable matches:

- Placeholder documentation such as `DEEPSEEK_API_KEY=your-key`.
- Redaction tests that intentionally contain fake secrets.
- Redacted examples such as `/Users/[REDACTED_USER]/...`.

Block the release when a real absolute path, key, token, raw private chat, or internal workflow file is tracked.

## 3. License And Third-Party Notices

Confirm that licensing is explicit and compatible with included assets.

Required checks:

- `LICENSE` exists and matches Apache-2.0.
- `NOTICE` exists.
- `THIRD_PARTY_NOTICES.md` exists when third-party names, logos, or integrations are included.
- README wording makes clear that third-party marks belong to their owners.

If a new logo, screenshot, icon, dataset, or bundled parser is added, review whether it needs attribution or should be linked instead of bundled.

## 4. Build And Test Gates

Run the local development gate:

```bash
scripts/dev-check.sh
```

The gate should cover:

- Python lint with Ruff.
- Local Markdown documentation link checks.
- Python unit tests.
- Frontend build.
- Frontend dependency audit and UI smoke.
- CLI smoke checks.
- Package build.

Known acceptable warnings should be documented. Unexpected test skips, uncaught exceptions, or build failures block the release.

## 5. Release Readiness Script

Run:

```bash
scripts/release-readiness.py
```

Expected result:

- `ready: true`.
- No tracked private paths.
- No tracked generated artifacts outside intentional package data.
- Required public files are present.

## 6. Clean Clone Smoke Test

Run the clean clone smoke script:

```bash
scripts/clean-clone-smoke.sh
```

This validates that a new user can install the project from a clean checkout without relying on local caches or ignored files.

## 7. Functional Smoke Matrix

At minimum, verify the following without requiring private data:

| Area | Smoke check | Blocks release |
| --- | --- | --- |
| CLI | `uv run knoar --help` and `uv run knoar doctor` | Yes |
| Service | `uv run knoar serve` starts and prints the UI URL | Yes |
| UI | `/` opens the bundled console and `/docs` opens API docs | Yes |
| Query | Query returns a structured response against a sample or existing vault | Yes |
| Ingest | A small Markdown source can be ingested into a temporary vault | Yes |
| Lint | Deterministic lint can scan the temporary vault and write a report | Yes |
| Reports | Ingest/lint/query reports are readable in the console | Yes |

External model-provider calls may be skipped only when credentials or network are unavailable. If skipped, note it in the release decision.

See [Testing And Quality Gates](TESTING.md) for the current automated and manual
test boundary.

## 8. API And CLI Compatibility

Review all public entry points before release:

- CLI commands documented in `docs/CLI.md`.
- HTTP endpoints documented in `docs/API.md`.
- Compatibility rules documented in `docs/API_COMPATIBILITY.md`.
- Stable error codes documented in `docs/ERROR_CODES.md`.
- Configuration fields documented in `docs/CONFIGURATION.md`.

Breaking changes require a changelog entry and migration note.

## 9. Documentation Review

Review both English and Chinese public docs:

- `README.md`
- `README.zh-CN.md`
- `docs/README.md`
- `docs/zh/README.md`
- `docs/QUICKSTART.md`
- `docs/zh/QUICKSTART.md`
- `docs/CONFIGURATION.md`
- `docs/zh/CONFIGURATION.md`
- `docs/API.md`
- `docs/zh/API.md`
- `docs/API_COMPATIBILITY.md`
- `docs/zh/API_COMPATIBILITY.md`
- `docs/CLI.md`
- `docs/zh/CLI.md`
- `docs/TROUBLESHOOTING.md`
- `docs/zh/TROUBLESHOOTING.md`
- `docs/BACKUP_AND_RECOVERY.md`
- `docs/zh/BACKUP_AND_RECOVERY.md`
- `docs/TESTING.md`
- `docs/zh/TESTING.md`
- `SUPPORT.md`
- `CODE_OF_CONDUCT.md`

The docs should explain:

- What KnoArbor is.
- What it is not.
- How to install and run it.
- How to configure a model provider.
- How ingest, lint, and query fit together.
- What data is written locally.
- Current public release boundaries.

## 10. UI Review

Open the management console and inspect:

- Navigation order and labels.
- Source settings.
- Ingest, lint, query run pages.
- Run monitor.
- Reports.
- Knowledge-base browser.
- Graph page.
- Settings.
- English and Chinese text.

Block release when the UI cannot load, core actions are hidden, report links are broken, or generated pages cannot be inspected.

## 11. Performance And Long-Run Safety

Review that long-running workflows expose:

- Queue state.
- Heartbeats.
- Cancellable run handles.
- Progress events.
- Written reports, including failure reports.
- File locks for writes.

The release does not require distributed queues, databases, or multi-user sessions, but single-machine behavior must be predictable.

## 12. Release Notes And Tagging

Before tagging:

- Update `CHANGELOG.md`.
- Add or update `docs/releases/vX.Y.Z.md`.
- Confirm `pyproject.toml` version.
- Commit all release changes.

Tag from `main` for public release:

```bash
git tag -a vX.Y.Z -m "KnoArbor vX.Y.Z"
git push origin main --tags
```

Use GitHub Releases to include:

- Short positioning statement.
- Major user-facing changes.
- Verification summary.
- Known limitations.
- Upgrade notes.

## Release Decision Template

```text
Version:
Commit:
Date:

Automated gates:
- dev-check:
- release-readiness:
- clean-clone-smoke:
- frontend build:

Manual gates:
- privacy:
- license:
- docs:
- UI:
- functional smoke:
- API/CLI compatibility:

Known limitations:
- ...

Decision:
- release / hold
```
