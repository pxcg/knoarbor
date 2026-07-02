# Documentation

This directory contains the long-form documentation for KnoArbor. The root README is the project overview; this page is the documentation index.

Chinese documentation lives in [zh/](zh/). This documentation tree is intended for public users and contributors.

## Document Taxonomy

- User guides: installation, quickstart, configuration, troubleshooting, and backup.
- Reference: CLI, API, and error-code lookup.
- Contracts: frozen API, UI, report, provenance, and runtime boundaries.
- Architecture: system boundaries, capability ownership, roadmap, and ADRs.
- Maintainer operations: development, testing, release, and long-term governance.
- Release history: changelog and version-specific release notes.

See [Documentation Governance](DOCUMENTATION_GOVERNANCE.md) for ownership and cleanup rules.

## User Guides

- [Showcase](SHOWCASE.md): product tour, end-to-end flow, demo path, and current boundaries.
- [Installation](INSTALLATION.md): local install, service startup, model setup, UI rebuild, and verification.
- [Quickstart](QUICKSTART.md): initialize a vault, compile the bundled example, open the local console, and verify Chat/query.
- [Configuration](CONFIGURATION.md): model providers, vault paths, connectors, document processing, and privacy redaction.
- [Troubleshooting](TROUBLESHOOTING.md): common setup, model, UI, ingest, and runtime issues.
- [Backup And Recovery](BACKUP_AND_RECOVERY.md): runtime vault backup, git recovery boundaries, and safe index rebuilds.
- [Core Concepts](CONCEPTS.md): raw sources, source documents, wiki pages, source audits, ingest, lint, query, and runtime vault.

## Reference

- [CLI Reference](CLI.md): command-line usage for ingest, lint, query, service, and debugging.
- [API Reference](API.md): FastAPI endpoints and boundary rules.
- [API Compatibility](API_COMPATIBILITY.md): stable endpoint policy, schema versioning, and deprecation rules.
- [Error Codes](ERROR_CODES.md): stable CLI/API error codes and troubleshooting hints.

## Contracts

- [Contracts](CONTRACTS.md): frozen vault, wiki, source digest, index, ingest, query, chat, API, and UI contracts.
- [UI Contract](UI_CONTRACT.md): chat-first console surfaces, UI-only adapters, and rendering boundaries.
- [Report Contract](REPORT_CONTRACT.md): reports, ledgers, failure artifacts, and token analysis boundaries.
- [Provenance Design](PROVENANCE_DESIGN.md): source chain semantics across raw sources, source digests, and knowledge pages.

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
- [Desktop App Spec](../specs/1.15-desktop-app/requirements.md): Electron desktop surface, packaged Python service, app-data, logs, and intranet update architecture.
- [Contributing](../CONTRIBUTING.md): contribution process, branch model, tests, and privacy rules.
- [Security](../SECURITY.md): vulnerability reporting and secret handling.
- [Support](../SUPPORT.md): where to ask questions and how to file useful reports.
- [Code Of Conduct](../CODE_OF_CONDUCT.md): contribution conduct expectations.

## Release History

- [Changelog](../CHANGELOG.md): public release notes.
- [v2.2.1 Release Notes](releases/v2.2.1.md): desktop patch release for chat evidence, image defaults, session refresh, and Windows packaging.
- [v2.0.0 Release Notes](releases/v2.0.0.md): desktop app and ingest upgrade release content.
- [v1.3.0 Release Notes](releases/v1.3.0.md): wiki-first chat, page-first retrieval, multi-vault workspace, and model configuration release content.
- [v1.2.1 Release Notes](releases/v1.2.1.md): model endpoint detection and local provider configuration release content.
- [v1.2.0 Release Notes](releases/v1.2.0.md): multi-vault configuration and skill integration release content.
- [v1.0.0 Release Notes](releases/v1.0.0.md): first public local-first release content.
- [v0.9.0 Release Notes](releases/v0.9.0.md): runtime endpoint, skill integration, and observability release content.
- [v0.8.0 Release Notes](releases/v0.8.0.md): API contract and token-observability release content.
- [v0.7.0 Release Notes](releases/v0.7.0.md): UI and knowledge-base browsing alpha release content.
- [v0.6.0 Release Notes](releases/v0.6.0.md): UI foundation release content.
- [v0.5.1 Release Notes](releases/v0.5.1.md): release-hardening patch for stable API contracts and live smoke validation.
- [v0.5.0 Release Notes](releases/v0.5.0.md): onboarding and diagnostics release content.
- [v0.4.0 Release Notes](releases/v0.4.0.md): multi-source ingest stability release content.
- [v0.3.0 Release Notes](releases/v0.3.0.md): reliability and evaluation release content.
- [v0.2.0 Release Notes](releases/v0.2.0.md): engine-foundation alpha release content.
- [v0.1.0 Release Notes](releases/v0.1.0.md): first public alpha release content.

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
