# 1.5 Knowledge Governance Design

## Authority Model

```text
raw material
  -> source record
  -> canonical facts + raw evidence
  -> knowledge atom index
  -> query indexes
  -> generated page projection
```

Raw-derived authority flows from left to right. A user edit is accepted only
through the projection-edit command, which parses supported fields and
publishes the next canonical revision; downstream Markdown is never copied
wholesale into canonical storage.

## Ownership

| Layer | Owner | Lint authority |
| --- | --- | --- |
| Raw material | source lifecycle | read and report |
| Source records / canonical facts / evidence | ingest | validate; execute reingest |
| Knowledge atoms | ingest publication | validate; execute reingest |
| Query indexes | index publication | validate; execute deterministic rebuild |
| Generated pages | projection renderer | validate; execute deterministic rebuild |
| Reports / ledgers | lint | write |

## Flow

```text
collect active canonical state
  -> deterministic integrity scan
  -> apply bounded derived-state repairs
  -> optional semantic quality diagnosis
  -> build owner-routed repair plan
  -> execute ingest / materialization owners
  -> rescan
  -> report / ledger
```

Semantic diagnosis is advisory. It receives bounded locator and canonical
evidence, returns findings, and cannot emit page drafts or executable content
patches.

## Repair Matrix

| Finding | Resolution |
| --- | --- |
| Missing or unreadable raw | report only |
| Missing source/facts/evidence association | reingest request |
| Invalid atom reference or semantic extraction concern | reingest request |
| Missing/stale machine index | index rebuild request |
| Missing/stale generated projection | projection rebuild request |
| Markdown presentation defect in generated page | projection rebuild request |
| Privacy finding in raw or canonical facts | report only; source lifecycle owns correction |
| External freshness or factual uncertainty | report only |

## Repair Plan Contract

Repair actions are data passed to owner workflows, not local patch operations:

```json
{
  "queue_type": "reingest_request | index_rebuild_request | projection_rebuild_request | report_only",
  "source_record_id": "optional stable source identity",
  "target": "source, index generation, or projection path",
  "issue_type": "stable issue code",
  "reason": "evidence-bound explanation",
  "evidence": []
}
```

The action is consumed automatically by the owning lifecycle. Lint does not
emulate that lifecycle through local page patches or repeated semantic retries.

## Projection Edit Contract

`source_index` projection edits reuse the existing canonical revision stream:

```text
submitted Markdown
  -> validate immutable identity / Source / Attachments / evidence
  -> parse synthesis / existing claims / entities / relations
  -> publish canonical revision with revision_origin=user_edit
  -> materialize projection and indexes
```

The revision stores `parent_revision_id` and `edited_fields` in existing
processing metadata and diagnostics. No second fact layer or user-revision
directory exists. A later raw ingest carries forward only those explicit
fields. New claims are rejected by the free-text editor because they do not
have a raw evidence identity; an evidence-aware operation is required to add
them.

## Removed Active Paths

- semantic draft compilation;
- model-authored `rewrite_section`, `improve_summary`,
  `remove_chatty_content`, and `strengthen_provenance` writes;
- direct page merge/split/delete governance;
- provenance page creation from projection text;
- automatic deferred semantic retry rounds.

Historical schemas may remain readable for stored reports during migration,
but new runs do not produce or execute those actions.

## Verification

- deterministic issue identities remain stable;
- semantic models do not author replacement facts or page patches;
- repair actions name their owning lifecycle and evidence;
- rebuild execution, when available, uses the same publication functions as
  ingest rather than a lint-specific writer;
- lint orchestrates repairs through the owning ingest or materialization
  workflow and verifies the resulting state with a deterministic rescan.
- reingest resolves the exact immutable `SourceDocument` from the active
  revision's owning input generation; source units are not concatenated into a
  synthetic replacement input.
