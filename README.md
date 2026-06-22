# KnoArbor

[English](README.md) | [简体中文](README.zh-CN.md)

<p align="center">
  <img src="docs/assets/knoarbor-logo.svg" alt="KnoArbor logo" width="112" height="112">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/status-1.3%20wiki--chat%20release-0f766e.svg" alt="1.3 wiki chat release status">
  <a href="docs/QUICKSTART.md"><img src="https://img.shields.io/badge/docs-quickstart-111827.svg" alt="Quickstart"></a>
</p>

KnoArbor is an AI-native wiki engine that compiles multi-source information into a traceable, maintainable knowledge network, helping scattered knowledge grow like a tree.

KnoArbor provides a durable knowledge layer for tools such as Hermes, Codex, Obsidian, local CLI workflows, and future AI assistants.

```text
Raw sources -> Ingest -> Markdown wiki -> Lint -> Query context
```

## At A Glance

| Area | What KnoArbor provides |
| --- | --- |
| Input | Markdown notes, AI chat sessions, generic chat logs, and optional MinerU-preprocessed rich documents |
| Output | A local Markdown wiki with source digests, entities, concepts, queries, reports, ledgers, and graph links |
| Interfaces | CLI, FastAPI, local management console, and host-AI skill template |
| Runtime model | Local-first, single-user, file-based vaults with queue, locks, checkpoints, and reports |

## Why KnoArbor

Most AI knowledge workflows either keep raw files and search them repeatedly, or let conversations disappear into long chat logs. KnoArbor follows a different pattern:

- keep raw sources immutable;
- compile useful content into maintained wiki pages;
- preserve provenance from generated pages back to sources;
- lint the wiki for structure, links, source chains, and quality;
- query the maintained wiki as evidence for a host AI.

This makes the wiki a reusable artifact, not a transient retrieval result.

## Features

- **Local-first vault**: generated pages live in a normal Markdown folder that can be opened in Obsidian.
- **Ingest pipeline**: converts supported sources into `source_document.v1`, extracts knowledge, plans page operations, reviews drafts, writes pages, and records reports.
- **Lint pipeline**: scans deterministic wiki issues, diagnoses structural/provenance/quality problems, reviews maintenance actions, and applies approved repairs.
- **Query pipeline**: returns ranked pages, excerpts, source pointers, graph context, and a context pack for external AI tools.
- **Wiki chat**: answers from maintained wiki pages with citations, source previews, and session history.
- **Source provenance**: separates raw sources, source digest pages, and generated knowledge pages.
- **Multi-vault profiles**: manage multiple named local knowledge bases from one configuration and query one or many vaults.
- **Model adapters**: works with DeepSeek, OpenAI, OpenRouter, LM Studio, vLLM-compatible endpoints, and native Ollama.
- **CLI, API, and local console**: run from terminal, HTTP API, or the bundled web UI served at `/` with `/ui` kept as a compatibility alias.
- **Skill integration**: includes a generic local wiki skill template for AI tools that can call a local HTTP service.

## Product Tour

The bundled local console helps configure sources, launch ingest/lint/query runs, inspect run state, view reports, and browse the generated wiki graph.

### Overview

Check service readiness, vault health, page counts, and recommended next steps before starting a workflow.

<p align="center">
  <img src="docs/assets/knoarbor-console-overview.png" alt="KnoArbor local console overview" width="920">
</p>

### Source Coverage

Inspect enabled source connectors and understand how raw inputs enter the shared ingest pipeline.

<p align="center">
  <img src="docs/assets/knoarbor-console-sources.png" alt="KnoArbor sources page" width="920">
</p>

### Run Monitor

Follow long-running ingest, lint, and query workflows with queue state, heartbeats, cancellation, and recent run records.

<p align="center">
  <img src="docs/assets/knoarbor-console-runs.png" alt="KnoArbor runs page" width="920">
</p>

### Knowledge Base Browser

Browse generated wiki pages, inspect metadata, links, backlinks, and open the exact pages written or modified by a workflow run.

<p align="center">
  <img src="docs/assets/knoarbor-console-wiki.png" alt="KnoArbor knowledge base browser" width="920">
</p>

### Wiki Chat And Query Context

Ask questions directly in the local console, inspect the cited wiki pages behind an answer, or retrieve the same page-first context pack for a host AI through Query and Skill integrations.

<p align="center">
  <img src="docs/assets/knoarbor-console-query.png" alt="KnoArbor query page" width="920">
</p>

### Reports And Graph

Read human-friendly run reports and inspect the generated knowledge network.

<p align="center">
  <img src="docs/assets/knoarbor-console-reports.png" alt="KnoArbor reports page" width="920">
</p>

<p align="center">
  <img src="docs/assets/knoarbor-console-graph.png" alt="KnoArbor graph page" width="920">
</p>

## Installation

Requirements:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- One model provider, either OpenAI-compatible or native Ollama

```bash
git clone https://github.com/pxcg/knoarbor.git
cd knoarbor
uv sync
```

For a complete local installation path, see [Installation](docs/INSTALLATION.md).

## Quick Start

Create local configuration and initialize a vault:

```bash
uv run knoar first-run --vault ./vaults/default
```

This creates `config.yaml`, initializes `./vaults/default`, and copies a small bundled
Markdown example to `vaults/default/raw/notes/agent-loop.md`.

Create `.env` and set at least one provider key:

```bash
cp .env.example .env
DEEPSEEK_API_KEY=your-key
```

Load environment variables:

```bash
set -a && source .env && set +a
```

Check local readiness before running semantic workflows:

```bash
uv run knoar doctor
```

Compile the bundled example into wiki pages:

```bash
uv run knoar ingest --connector markdown --write
uv run knoar lint --mode structural
```

Start the local service:

```bash
uv run knoar serve
```

Open the local console:

```text
http://127.0.0.1:8000
```

In the console, open Chat and ask:

```text
Agent Loop 是什么？
```

You can also query the maintained wiki from the terminal:

```bash
uv run knoar query "Agent Loop 是什么？"
```

The full command `knoarbor` is also available:

```bash
uv run knoarbor --help
```

## Core Concepts

KnoArbor organizes knowledge into three layers:

```text
vaults/
└── default/
    ├── pages/        # Obsidian-facing wiki; open this directory in Obsidian
    │   ├── *.md          # maintained knowledge pages
    │   ├── sources/      # source digest pages
    │   └── _views/       # generated browsing views
    ├── raw/          # immutable source files
    ├── maintenance/  # human-readable run reports
    └── .knoarbor/    # machine state, indexes, ledgers, locks, runs
```

The runtime `vaults/` workspace is ignored by git because it can contain private notes, source documents, generated pages, and run records. Use `vaults/default/pages` as the clean Obsidian vault when you only want maintained Wiki pages.
Knowledge-page type is metadata, not a required physical directory: pages carry `page_kind`, `role`, `facets`, claims, and typed relations. Source digest pages stay under `pages/sources/`; generated `_views/` pages provide Obsidian-friendly browsing by concepts, entities, workflows, comparisons, open questions, and source audit.

## Usage

### Ingest sources

Inspect configured source connectors before running semantic ingest:

```bash
uv run knoar sources --connector codex --json
```

For first-run troubleshooting, use the read-only doctor command:

```bash
uv run knoar doctor --connector markdown
uv run knoar doctor --json
```

The JSON preflight output is compact by default. Add `--include-content` only
when you need the full normalized source document payload.

Run all enabled connectors from `config.yaml`:

```bash
uv run knoar ingest --write
```

Long-running CLI workflows are progress-first by default. `ingest` and `lint` follow the local run queue and print event /
heartbeat lines for human-readable output. Use `--json` for pure structured
output or `--no-follow` for synchronous summary output.

Run one connector:

```bash
uv run knoar ingest --connector markdown --write
uv run knoar ingest --connector hermes --write
uv run knoar ingest --connector openclaw --write
```

Run a single prepared `source_document.v1`:

```bash
uv run knoar ingest --source-document /path/to/source_document.json --write
```

Run one file or folder path:

```bash
uv run knoar ingest --input /path/to/note.md --write
uv run knoar ingest --input /path/to/paper.pdf --write
uv run knoar ingest --input /path/to/folder --write
```

Markdown files enter ingest directly. Folder input discovers Markdown files
recursively by default. Non-Markdown files require a configured MinerU-compatible
preprocessor; if it is missing or unreachable, the run fails with an explicit
configuration error. KnoArbor does not redistribute MinerU or its model weights;
users who enable the adapter should install MinerU separately and follow MinerU's
license and attribution requirements.

### Maintain the wiki

Structural repair:

```bash
uv run knoar lint --mode structural
```

Quality review:

```bash
uv run knoar lint --mode quality
```

Full maintenance with approved writes:

```bash
uv run knoar lint --mode full --apply-reviewed
```

### Query context

```bash
uv run knoar query "What does this wiki know about Agent Loop?"
uv run knoar query --json "Agent Loop control patterns"
```

Query is retrieval-only. KnoArbor returns context and evidence; the host AI is responsible for the final answer.

## Current Status

KnoArbor is in the 1.x local-first release line. The core local workflows, CLI, stable HTTP API, bundled console, multi-vault configuration, and host-AI skill template are intended to be usable as a single-user local knowledge engine.

Implemented today:

- Markdown, Hermes session, Codex session, OpenClaw session, Claude Code session, and generic chat source connectors.
- Optional MinerU-compatible document preprocessing into Markdown.
- Ingest, lint, and query pipelines in Python Core.
- FastAPI service and CLI entry points.
- Local React console bundled with the Python package.
- Runtime wiki initialization, machine index, queue, locks, ledgers, reports, and checkpoints.
- Multi-vault configuration, query, run/report listing, and skill drilldown.

Not included in the current local-first release:

- Hosted SaaS deployment.
- Built-in vector database.
- Built-in chat answer generation.
- Built-in MinerU model/runtime.
- Packaged external workflow templates.

## Configuration

Model providers are configured in `config.yaml`, while secrets stay in `.env`:

```yaml
models:
  default_provider: deepseek
  default_max_tokens: 30000
  request_timeout_seconds: 600
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key_env: DEEPSEEK_API_KEY
      model: deepseek-v4-flash
```

Model providers run through the ModelGateway boundary. OpenAI-compatible endpoints work by default; Ollama can also use a native `/api/chat` adapter for local thinking models. Local endpoints such as Ollama or vLLM can run without `api_key_env`. See [Configuration](docs/CONFIGURATION.md) for provider examples and connector settings.

## Architecture

KnoArbor is a workflow-first system with narrow semantic contracts:

```text
Connectors
  -> Source Pipeline
  -> Semantic Contracts
  -> Write Pipeline
  -> Lint Maintenance
  -> Query Retrieval
```

Main package layout:

```text
src/knoarbor/
├── entrypoints/       # FastAPI app and routers
├── services/          # API-to-pipeline adapters
├── pipelines/         # ingest, lint, query, write orchestration
├── connectors/        # source discovery and conversion
├── semantic/          # prompts, contracts, model client
├── storage/           # vault, index, paths, ledgers, writer
├── retrieval/         # search, links, Markdown extraction
├── maintenance/       # lint scan and operation execution
├── presenters/        # API/CLI/skill response shaping
└── core/              # schemas, config, redaction, common rules
```

See [Architecture](docs/ARCHITECTURE.md) and [Provenance Design](docs/PROVENANCE_DESIGN.md) for the detailed design.

## Documentation

- [Showcase](docs/SHOWCASE.md)
- [Quickstart](docs/QUICKSTART.md)
- [Configuration](docs/CONFIGURATION.md)
- [CLI Reference](docs/CLI.md)
- [API Reference](docs/API.md)
- [API Compatibility](docs/API_COMPATIBILITY.md)
- [Core Concepts](docs/CONCEPTS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Backup And Recovery](docs/BACKUP_AND_RECOVERY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Provenance Design](docs/PROVENANCE_DESIGN.md)
- [Roadmap](docs/ROADMAP.md)
- [Testing And Quality Gates](docs/TESTING.md)
- [Development](docs/DEVELOPMENT.md)
- [Contributing](CONTRIBUTING.md)
- [Support](SUPPORT.md)
- [Changelog](CHANGELOG.md)
- [Security](SECURITY.md)

## Development

Run the current required checks:

```bash
scripts/dev-check.sh
```

For release candidates, use `scripts/release-check.sh`. It runs the local gate plus release-readiness and clean-clone smoke checks.

When a real DeepSeek-compatible provider is available, also run:

```bash
set -a && source .env && set +a
scripts/live-release-candidate-smoke.sh
```

This validates the live `ingest -> lint -> query` path on temporary Markdown
and chat sources, plus the explicit non-Markdown preprocessor error path.

See [Development](docs/DEVELOPMENT.md) for package layout and contribution notes.

## Security and Privacy

KnoArbor is designed for local-first use. Raw sources and generated wiki pages can contain private information. Do not commit runtime vault data.

Ignored by default:

- `.env`
- `config.yaml`
- `config.local.yaml`
- `vaults/`
- `.local-dev/`
- `.venv/`
- `.uv-cache/`

Report security issues through [SECURITY.md](SECURITY.md).

## Star History

<a href="https://www.star-history.com/#pxcg/knoarbor&Date">
  <img src="https://api.star-history.com/svg?repos=pxcg/knoarbor&type=Date" alt="KnoArbor star history" />
</a>

## License

KnoArbor is licensed under the [Apache License 2.0](LICENSE).

```text
Copyright 2026 KnoArbor contributors
```

See [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution, third-party icon, and project identity notes. The Apache-2.0 license does not grant trademark rights to the KnoArbor name.
