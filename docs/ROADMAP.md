# Roadmap

KnoArbor has moved past the original 1.x to 2.0 compatibility baseline. The
active direction is desktop-first: keep the Python/FastAPI core as the execution
engine, and make the desktop app the primary user surface for chat, vault
operation, configuration, reports, wiki browsing, and packaging.

This roadmap is directional planning. Capability state is tracked in
[Capability Map](CAPABILITY_MAP.md), durable decisions live in
[ADRs](adr/README.md), and multi-step implementation work belongs in
[`specs/`](../specs/README.md).

## Current Priorities

| Theme | Direction | Outcome |
| --- | --- | --- |
| Desktop app | Treat Electron as the primary product shell while keeping the web bundle as an embedded UI asset. | Users operate KnoArbor from one desktop app instead of a separate source-built web workflow. |
| Vault portability | Make vault data, chat sessions, attachments, generated images, reports, and indexes easy to back up and move between machines. | A user can migrate a desktop vault without losing conversation evidence or local assets. |
| Wiki-first chat | Keep chat bounded to KnoArbor tools, page evidence, citations, attachments, and image generation defaults. | Chat answers are inspectable and tied back to maintained wiki pages and source evidence. |
| Ingest stability | Keep source normalization, document preprocessing, segmentation, write policy, and reports reliable before adding broad new source types. | Rich documents and long conversations enter the same traceable ingest path. |
| Configuration clarity | Reduce overlapping config discovery, legacy migration, and redundant fallback paths as the desktop baseline stabilizes. | Desktop and service configuration behave predictably across upgrades. |
| Packaging and release | Use automated macOS and Windows builds, release notes, and clean repository gates. | Releases carry the desktop app artifacts users actually install. |
| Documentation hygiene | Keep public docs focused on current surfaces; archive one-off governance reviews separately. | Users and maintainers can tell which document owns each decision. |

## Later Horizons

These capabilities remain useful but should not distract from the desktop-first
baseline:

- optional vector retrieval behind the index contract;
- richer external source connectors;
- collaborative or cloud synchronization workflows;
- hosted multi-user service;
- broader document-processing provider choices;
- advanced graph analytics beyond page relationships.

## Non-Goals

KnoArbor should remain a local-first knowledge engine that other tools can use.
It should not become:

- a generic chat assistant;
- a hidden browser or filesystem automation agent;
- a mandatory cloud service;
- a bundled large-model distribution;
- a system that rewrites user vault data without traceable reports.

## Guiding Principles

- Prefer stable contracts over feature breadth.
- Keep source connectors narrow and testable.
- Keep semantic agents focused on decisions that require language understanding.
- Keep deterministic validation outside the model.
- Do not hide failures behind broad fallbacks; expose actionable errors and reports.
- Treat the vault as user data and never overwrite it during tests or initialization.
- Make every generated or maintained page traceable to source evidence.
