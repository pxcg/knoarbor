# Documentation

This directory contains the long-form documentation for KnoArbor. The root README is the project overview; this page is the documentation index.

Chinese documentation lives in [zh/](zh/). This documentation tree is intended for public users and contributors.

## Start Here

- [Showcase](SHOWCASE.md): product tour, end-to-end flow, demo path, and current boundaries.
- [Quickstart](QUICKSTART.md): install, configure, initialize a vault, run the service, and try query.
- [Configuration](CONFIGURATION.md): model providers, vault paths, connectors, document processing, and privacy redaction.
- [CLI Reference](CLI.md): command-line usage for ingest, lint, query, service, and debugging.
- [API Reference](API.md): FastAPI endpoints and boundary rules.
- [Error Codes](ERROR_CODES.md): stable CLI/API error codes and troubleshooting hints.
- [Core Concepts](CONCEPTS.md): raw sources, source documents, wiki page types, ingest, lint, query, and runtime vault.

## Architecture

- [Architecture](ARCHITECTURE.md): current system architecture and implementation boundaries.
- [Provenance Design](PROVENANCE_DESIGN.md): source chain semantics across raw sources, source digests, and knowledge pages.

## Operations

- [Release Preflight Checklist](RELEASE_CHECKLIST.md): repository, privacy, tests, docs, UI, and release gates before tagging.
- [Changelog](../CHANGELOG.md): public release notes.
- [v0.7.0 Release Notes](releases/v0.7.0.md): UI and knowledge-base browsing alpha release content.
- [v0.6.0 Release Notes](releases/v0.6.0.md): UI foundation release content.
- [v0.5.1 Release Notes](releases/v0.5.1.md): release-hardening patch for stable API contracts and live smoke validation.
- [v0.5.0 Release Notes](releases/v0.5.0.md): onboarding and diagnostics release content.
- [v0.4.0 Release Notes](releases/v0.4.0.md): multi-source ingest stability release content.
- [v0.3.0 Release Notes](releases/v0.3.0.md): reliability and evaluation release content.
- [v0.2.0 Release Notes](releases/v0.2.0.md): engine-foundation alpha release content.
- [v0.1.0 Release Notes](releases/v0.1.0.md): first public alpha release content.

## Development

- [Development](DEVELOPMENT.md): setup, tests, package layout, design rules, and release notes.
- [Contributing](../CONTRIBUTING.md): contribution process, branch model, tests, and privacy rules.
- [Security](../SECURITY.md): vulnerability reporting and secret handling.

## Reading Order

For users:

```text
Showcase -> Quickstart -> Configuration -> CLI Reference -> Core Concepts
```

For contributors:

```text
Core Concepts -> Architecture -> Provenance Design -> Development -> Contributing
```

For release preparation:

```text
Release Preflight Checklist -> Changelog -> Release Notes -> Security
```
