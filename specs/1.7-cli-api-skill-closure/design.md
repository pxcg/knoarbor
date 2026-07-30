# 1.7 CLI, API, And Skill Closure Design

## Owning Layers

| Layer | Responsibility |
| --- | --- |
| API | Stable HTTP contracts and response envelopes. |
| CLI | Human/machine command-line adapter over core services. |
| Skill | Host-AI operation instructions and thin HTTP helper. |
| Services / Pipelines | Shared implementation behind all entry points. |
| Runtime | Run IDs, events, cancellation, runtime discovery. |

## Surface Alignment

Public capability families:

- health;
- runtime;
- doctor;
- sources;
- ingest;
- lint;
- query;
- reports;
- runs;
- wiki pages.

Each entry point should map to these families rather than inventing a different
workflow vocabulary.

## CLI Boundary

The CLI exposes stable human and JSON operations for:

- setup and diagnostics: `first-run`, `init`, `serve`, `status`, `doctor`;
- source preflight: `sources`;
- write workflows: `ingest`, `lint`;
- retrieval and feedback: `query`, `query-feedback`;
- maintained artifacts: `pages`, `reports`;
- run lifecycle: `runs`.

`pages` and `reports` are read-only mirrors of the public `/wiki/pages*` and
`/reports*` APIs. They give terminal users the same drilldown path that host-AI
skills use after query, ingest, or lint runs.

Model provider discovery and capability writeback remain API/UI-oriented for
now. They are configuration tasks with form-like state, and adding equivalent
CLI commands is deferred until command shape is worth freezing.

## Skill Boundary

The bundled host-AI skill lives at `integrations/skills/knoarbor-local`.
Category folders are intentionally avoided because the package spans query,
page reading, reports, run inspection, ingest, and lint operations.

The skill should:

- discover service and vault context;
- call public APIs;
- return context, page content, reports, run status, or operation results;
- leave final answer generation to the host AI.

The skill should not:

- call `/ui/api/*`;
- reimplement retrieval or report parsing when public endpoints exist;
- require hardcoded local project paths;
- start a long-running background daemon.

## Response Shape

Workflow APIs should preserve envelope shape:

```json
{
  "schema_version": "workflow_response.v1",
  "flow": "ingest",
  "execution": "queued",
  "status": "queued",
  "run_id": "...",
  "run": {},
  "result": null
}
```

CLI `--json` should expose the same concepts. Human output can summarize but
should not hide report paths, run IDs, or error codes.

`/query` keeps its own retrieval schema (`wiki_query.v2`) because it is a
read-only evidence endpoint, not a workflow run envelope.

## Rejected Alternatives

### Separate Skill-Specific API

Rejected because it would create a second integration surface and weaken public
API closure.

### Query Generates Final Answers

Rejected because host AI tools already own conversation context and answer
generation. KnoArbor returns evidence/context.

### Preserve Prototype Endpoints

Rejected for pre-2.0 development. Clarity is more important than compatibility
with unannounced prototypes.
