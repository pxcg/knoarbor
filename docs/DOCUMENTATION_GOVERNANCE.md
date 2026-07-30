# Documentation Governance

This file defines how KnoArbor documentation is classified and when documents
should be merged, archived, or removed.

## Document Classes

| Class | Current location | Owns | Should not contain |
| --- | --- | --- | --- |
| User guides | `docs/QUICKSTART.md`, `docs/INSTALLATION.md`, `docs/CONFIGURATION.md`, `docs/TROUBLESHOOTING.md`, `docs/BACKUP_AND_RECOVERY.md`, `docs/CONCEPTS.md` | First-run use, normal operation, recovery, setup decisions, stable concepts | Internal implementation debates or release process |
| Product tour | `docs/SHOWCASE.md`, root `README.md` | What the product does and what to show in demos | Full API/CLI references |
| Reference | `docs/API.md`, `docs/CLI.md`, `docs/ERROR_CODES.md` | Stable command, route, and error lookup | Architecture rationale or roadmap prose |
| Contracts | `docs/CONTRACTS.md`, `docs/API_COMPATIBILITY.md`, `docs/UI_CONTRACT.md`, `docs/REPORT_CONTRACT.md`, `docs/PROVENANCE_DESIGN.md` | Frozen runtime, API, UI, report, and provenance boundaries | Temporary implementation notes |
| Architecture | `docs/ARCHITECTURE.md`, `docs/CAPABILITY_MAP.md`, `docs/ROADMAP.md`, `docs/adr/` | Stable boundaries, accepted decisions, capability status, long-term direction | Sprint notes or unresolved experiments |
| Maintainer operations | `docs/DEVELOPMENT.md`, `docs/MAINTAINERS.md`, `docs/TESTING.md`, `docs/RELEASE_CHECKLIST.md` | Local development, release gates, branch policy, quality gates | User onboarding content duplicated from guides |
| Release history | `docs/releases/`, `CHANGELOG.md` | Version-specific changes | Current supported behavior unless explicitly marked historical |
| Feature specs | `specs/<feature>/` | Feature requirements, accepted design, implementation status, and verification | Stable public contracts or duplicate roadmap prose |
| Spec lifecycle registry | `specs/registry.json` | The lifecycle, owner domain, and successor of every spec directory | Design prose or task details |

The root `docs/` directory remains intentionally flat for public English docs
because many README, release, and package links point there. Use the document
class above as the primary ownership boundary. Avoid moving stable public files
unless the whole docs tree is migrated in one planned pass.

## Cleanup Rules

- Current public prose uses **KnoArbor** as the product and company-repository
  name. Preserve lowercase technical identifiers such as the `knoarbor` Python
  package, `.knoarbor` data directory, schemas, and the `knoar` CLI. Do not
  rename historical versioned release notes only to update branding.
- Merge documents when two files answer the same reader question with the same
  authority. Keep the more stable owner and link to it from the secondary file.
- Delete documents when they describe removed scripts, removed UI surfaces, or
  local runtime artifacts that are no longer part of the product.
- Archive historical material only when it records a decision, migration, or
  release state that remains useful for maintainers.
- Keep release notes historically accurate. Do not rewrite old release notes to
  match the current product, except for secrets or broken repository links.
- Keep English and Chinese public docs aligned for user-visible behavior. It is
  acceptable for internal governance notes to exist only in Chinese.
- Specs under `specs/` are implementation bridges, not public docs. Promote only
  accepted, stable behavior from specs into `docs/`.
- `specs/registry.json` is the only authority for spec lifecycle and successor
  relationships. Status prose inside a spec must agree with the registry.
- Current specs in `Proposed`, `Accepted`, or `Implemented` lifecycle keep all
  four core files. Historical and superseded records may retain their original
  incomplete shape; maintainers do not invent missing historical documents.
- A new spec is created only when no current spec owns the proposed contract.
  Otherwise update the smallest current owner set.
- Accepted ADRs are immutable except for lifecycle and successor links. A new
  ADR supersedes a durable decision that changed.
- English is authoritative for versioned release notes. Chinese public guides,
  references, contracts, architecture, and maintainer documents remain paired.

## Current Policy

The active documentation set follows these ownership rules:

- keep public docs flat for now;
- keep feature specs outside public docs;
- delete one-off governance reviews after accepted conclusions move into the
  owning contract, ADR, or maintainer rule;
- remove docs for deleted product surfaces rather than preserving compatibility
  prose for them;
- prefer updating the owning document over duplicating explanations.
- run `scripts/check-doc-governance.py` and `scripts/check-doc-links.py` in the
  local and release gates.
