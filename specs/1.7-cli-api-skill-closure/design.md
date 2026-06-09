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

## Skill Boundary

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
