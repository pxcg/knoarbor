# Documentation

This directory contains the long-form documentation for KnoArbor. The root README is the project overview; this page is the documentation index.

Chinese documentation lives in [zh/](zh/). This documentation tree is intended for public users and contributors.

KnoArbor is the product and company-repository name. The compatibility names
`knoarbor` (Python package and local data namespace) and `knoar` (CLI) remain
intentional technical identifiers and are not alternate product names.

## Document Taxonomy

- User guides: installation, quickstart, configuration, troubleshooting, and backup.
- Reference: CLI, API, and error-code lookup.
- Contracts: frozen API, UI, report, provenance, and runtime boundaries.
- Architecture: system boundaries, capability ownership, roadmap, and ADRs.
- Maintainer operations: development, testing, release, and long-term governance.
- Release history: changelog and version-specific release notes.

See [Documentation Governance](DOCUMENTATION_GOVERNANCE.md) for ownership and cleanup rules.

## Product Tour

- [Showcase](SHOWCASE.md): product tour, end-to-end flow, demo path, and current boundaries.

## User Guides
- [Installation](INSTALLATION.md): local install, service startup, model setup, UI rebuild, and verification.
- [Quickstart](QUICKSTART.md): initialize a vault, compile the bundled example, open the local console, and verify Chat/query.
- [Configuration](CONFIGURATION.md): model providers, vault paths, connectors, document processing, and privacy redaction.
- [Troubleshooting](TROUBLESHOOTING.md): common setup, model, UI, ingest, and runtime issues.
- [Backup And Recovery](BACKUP_AND_RECOVERY.md): runtime vault backup, git recovery boundaries, and safe index rebuilds.
- [Core Concepts](CONCEPTS.md): raw sources, source documents, wiki pages, source audits, ingest, lint, query, and runtime vault.

## Reference

- [CLI Reference](CLI.md): command-line usage for ingest, lint, query, service, and debugging.
- [API Reference](API.md): FastAPI endpoints and boundary rules.
- [Error Codes](ERROR_CODES.md): stable CLI/API error codes and troubleshooting hints.

## Contracts

- [Contracts](CONTRACTS.md): frozen vault, wiki, source record, index, ingest, query, chat, API, and UI contracts.
- [API Compatibility](API_COMPATIBILITY.md): stable endpoint policy, schema versioning, and deprecation rules.
- [UI Contract](UI_CONTRACT.md): chat-first console surfaces, UI-only adapters, and rendering boundaries.
- [Report Contract](REPORT_CONTRACT.md): reports, ledgers, failure artifacts, and token analysis boundaries.
- [Provenance Design](PROVENANCE_DESIGN.md): source chain semantics across raw sources, source records, and knowledge pages.

## Architecture

- [Architecture](ARCHITECTURE.md): current system architecture and implementation boundaries.
- [Architecture Decision Records](adr/README.md): durable architecture decisions and ADR template.
- [Roadmap](ROADMAP.md): desktop-first current direction and later product horizons.
- [Capability Map](CAPABILITY_MAP.md): cross-feature capability status and ownership map.

## Contributors And Maintainers

- [Release Preflight Checklist](RELEASE_CHECKLIST.md): repository, privacy, tests, docs, UI, and release gates before tagging.
- [Testing And Quality Gates](TESTING.md): unit tests, frontend smoke, release checks, and live model smoke boundaries.
- [Development](DEVELOPMENT.md): setup, tests, package layout, design rules, and release notes.
- [Maintainer Guide](MAINTAINERS.md): long-term branch, architecture, fallback, compatibility, and release governance.
- [Documentation Governance](DOCUMENTATION_GOVERNANCE.md): document classes, ownership, cleanup, and archival rules for maintainers.
- [Feature Specs](../specs/README.md): implementation records for multi-step architecture or contract changes.
- [Contributing](../CONTRIBUTING.md): contribution process, branch model, tests, and privacy rules.
- [Security](../SECURITY.md): vulnerability reporting and secret handling.
- [Support](../SUPPORT.md): where to ask questions and how to file useful reports.
- [Code Of Conduct](../CODE_OF_CONDUCT.md): contribution conduct expectations.

## Release History

- [Changelog](../CHANGELOG.md): public release notes.
- [Release Notes Index](releases/README.md): complete versioned release-note navigation and historical policy.
- [v2.5.3 Release Notes](releases/v2.5.3.md): factual revisions, unified Raw retrieval, current renderer, and public desktop contracts.

Historical release notes preserve the endpoint names, command examples, and runtime assumptions from the version they describe. Use the API, contracts, and compatibility documents above for the current supported surface.

## Reading Order

For users:

```text
Showcase -> Installation -> Quickstart -> Configuration -> Troubleshooting -> CLI Reference -> Core Concepts
```

For contributors:

```text
Core Concepts -> Architecture -> Contracts -> Provenance Design -> API Compatibility -> Roadmap -> Feature Specs -> Development -> Maintainer Guide -> Testing -> Contributing
```

For release preparation:

```text
Release Preflight Checklist -> Testing -> Backup And Recovery -> Changelog -> Release Notes -> Security
```
