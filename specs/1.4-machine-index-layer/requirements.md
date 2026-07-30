# 1.4 Machine Index Layer Requirements

## Status And Ownership

Accepted. This specification owns immutable machine-index publication,
verification, navigation and lexical retrieval artifacts, rebuildability, and
future freshness diagnostics. Specification 1.38 exclusively owns lexical
document meaning, default knowledge-query ranking, and evidence resolution.

## Required Invariants

1. Machine indexes are rebuildable projections, never factual authority.
2. A build writes a complete immutable generation under
   `.knoarbor/index/generations/` and verifies every artifact before publication.
3. `.knoarbor/index/CURRENT` atomically selects exactly one verified generation.
4. Readers open one composite snapshot and do not mix artifacts from different
   navigation, retrieval, or factual generations.
5. Page, link, source, search, and graph artifacts serve UI navigation and
   diagnostics; default query does not rank their page prose.
6. Missing, stale, corrupt, or FTS5-incapable snapshots produce explicit typed
   diagnostics or a lifecycle-owned rebuild request, not a fallback to a second
   factual/retrieval authority.
7. Rebuild never mutates active factual revisions or user-authored raw material.
8. A retrieval cursor binds the retrieval generation, not a navigation-only
   generation change.

## Current Capability

- deterministic publication of `pages.json`, `links.json`, `sources.json`,
  `search.json`, and `graph_index.json`;
- content-addressed generation identity and per-file integrity hashes;
- atomic `CURRENT` publication;
- shared verified snapshot reader for graph and page navigation;
- materialization recovery through the ingest lifecycle owner.

## Remaining Scope

- user-facing freshness diagnostics;
- an explicit rebuild/status surface when its API, CLI, and report contracts are
  ready to be frozen;
- one SQLite FTS5 lexical snapshot for the atom/claim and Raw locator channels
  defined by 1.38;
- composite generation identity with independent navigation and retrieval
  generation IDs;
- reusable normalized revision shards and packaged-runtime FTS5 capability
  diagnostics.

## Non-Goals

- page-first default query;
- a Markdown scanning fallback behind an unused provider abstraction;
- mandatory vector storage or an external search service;
- a custom postings or per-request BM25 fallback beside FTS5;
- treating `index.md`, projection Markdown, or index JSON as factual authority.

## Retrieval Snapshot Replacement

The composite generation binds navigation, lexical, and active-fact generation
identities. Active factual revisions compile one verified lexical snapshot for
the atom/claim and Raw channels. Relation atoms remain ordinary atom documents;
their `source_claim_ids` close matches to Claims and then active Raw. No
relation-graph artifact or graph-specific generation identity is published.

Startup treats an unreadable or unsupported generation as a lifecycle-owned
clean rebuild request. Query readers never rebuild inline, migrate factual
data, or retain a compatibility reader.
