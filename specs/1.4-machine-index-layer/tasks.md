# 1.4 Machine Index Layer Tasks

## Completed

- [x] Publish immutable, content-addressed index generations.
- [x] Verify the exact artifact set and per-file hashes before use.
- [x] Select one generation through atomic `CURRENT` replacement.
- [x] Route graph and page navigation readers through `IndexSnapshot`.
- [x] Keep default knowledge query on the 1.38 atom/claim/evidence authority.
- [x] Delete disconnected Graph-led and page-provider implementations.

## Remaining

- [ ] Define user-facing freshness status without adding a second lifecycle owner.
- [ ] Freeze rebuild CLI/API/report contracts before exposing them publicly.
- [ ] Replace the navigation-only manifest with the composite navigation,
  retrieval, and active-fact generation contract.
- [ ] Add reusable normalized revision shards and one globally built SQLite
  FTS5 `LexicalSnapshot` for the document semantics owned by 1.38.
- [ ] Verify FTS5 capability in supported Python and packaged desktop runtimes;
  fail explicitly without another scorer.
- [ ] Publish/recover retrieval generations atomically with existing
  materialization lifecycle ownership.

## Deferred

- mandatory vector database;
- hosted search service;
- cross-device index synchronization.

## Two-Channel Snapshot Revision

- [x] Keep Claim, Entity, and Relation documents in the atom/claim FTS channel.
- [x] Resolve Relation matches through batch-local `source_claim_ids`.
- [x] Exclude synthesis and graph artifacts from the retrieval snapshot.
- [x] Publish lexical and navigation generations through one fact-fenced
  atomic `CURRENT`.
- [ ] Prove deterministic rebuild, crash safety, packaged SQLite capability,
  and old-revision exclusion.
