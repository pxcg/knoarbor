# KnoArbor

[English](README.md) | [简体中文](README.zh-CN.md)

<p align="center">
  <img src="docs/assets/knoarbor-logo.svg" alt="KnoArbor logo" width="112" height="112">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/status-2.5.3%20desktop%20release-0f766e.svg" alt="2.5.3 desktop release status">
  <a href="docs/QUICKSTART.md"><img src="https://img.shields.io/badge/docs-quickstart-111827.svg" alt="Quickstart"></a>
</p>

KnoArbor is a local-first AI knowledge system for compiling documents,
conversations, and notes into traceable knowledge that can be maintained and
queried over time.

```text
Local sources -> evidence units -> knowledge indexes -> raw-grounded answers
                                  -> readable Markdown projections
```

## What It Does

- imports Markdown, supported chat histories, and optionally preprocessed rich
  documents;
- preserves immutable source material and evidence-backed source revisions;
- extracts entities, claims, and relations as semantic retrieval metadata;
- retrieves raw evidence and source units for factual answers;
- maintains readable Markdown projections and a local knowledge graph;
- exposes the same vault through the desktop app, CLI, local HTTP API, and host
  AI skill integration;
- records local reports, ledgers, citations, and recovery state.

KnoArbor runs locally for an individual user. File operations and vault state
remain local; configured model APIs are the principal network capability.

## Workspace

<p align="center">
  <img src="docs/assets/knoarbor-desktop-chat.png" alt="KnoArbor desktop chat workspace" width="920">
</p>

The desktop workspace provides Chat, ingest and maintenance flows, source and
report inspection, Wiki browsing, and graph navigation. See the
[Showcase](docs/SHOWCASE.md) for the full product tour.

## Install

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and a configured
model provider.

```bash
git clone https://github.com/pxcg/KnoArbor.git
cd KnoArbor
uv sync
```

See [Installation](docs/INSTALLATION.md) for provider, desktop, and document
processing setup.

## First Run

```bash
uv run knoar first-run --vault ./vaults/default
uv run knoar doctor
uv run knoar ingest --connector markdown --write
uv run knoar serve
```

Then open `http://127.0.0.1:8000`. The complete guided path is in
[Quickstart](docs/QUICKSTART.md).

## Storage Model

- `raw/` contains source-faithful inputs and deterministic derivatives.
- `.knoarbor/facts/` and `.knoarbor/ingest.sqlite` contain published
  factual ingest state.
- `wiki/pages/` contains authored pages and deterministic readable projections.
- `.knoarbor/index/` contains rebuildable machine indexes.
- `maintenance/reports/` and `.knoarbor/ledgers/` contain audit material.

Raw evidence and source units are factual answer material. Wiki pages and atom
metadata are semantic locators and readable projections. See
[Core Concepts](docs/CONCEPTS.md), [Architecture](docs/ARCHITECTURE.md), and
[Provenance](docs/PROVENANCE_DESIGN.md).

## Documentation

- [Documentation Index](docs/README.md)
- [Showcase](docs/SHOWCASE.md)
- [Quickstart](docs/QUICKSTART.md)
- [Configuration](docs/CONFIGURATION.md)
- [CLI Reference](docs/CLI.md)
- [API Reference](docs/API.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Backup And Recovery](docs/BACKUP_AND_RECOVERY.md)
- [Contracts](docs/CONTRACTS.md)
- [Development](docs/DEVELOPMENT.md)
- [Changelog](CHANGELOG.md)

## Development

```bash
python scripts/plan-affected-validation.py
```

The planner reports mechanically required gates and the focused-test review
that still requires engineering judgment. Release candidates use
`scripts/release-check.sh`. Development and release workflow details belong to [Development](docs/DEVELOPMENT.md),
[Testing](docs/TESTING.md), and the
[Release Checklist](docs/RELEASE_CHECKLIST.md).

## Privacy And Security

Runtime vaults, local config, model credentials, and generated reports may
contain private information and are excluded from source control by default.
Do not commit API keys or personal vault content. Report vulnerabilities through
[SECURITY.md](SECURITY.md).

## License

KnoArbor is licensed under the [Apache License 2.0](LICENSE). See
[NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for
attribution and trademark notes.
