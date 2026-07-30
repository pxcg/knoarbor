import { requestJson } from "./http";
import { selectorToBody } from "./scope";
import type { VaultSelector, WorkflowResponse } from "./types";

export async function runIngest(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/ingest", { method: "POST", body: { execution: "queued", kind: "connectors", ...body } });
}

export async function runIngestFile(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/ingest", { method: "POST", body: { execution: "queued", kind: "file", ...body } });
}

export async function runIngestFolder(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/ingest", { method: "POST", body: { execution: "queued", kind: "folder", ...body } });
}

export async function ingestExcerpt(
  selector: VaultSelector,
  body: {
    excerpt_text: string;
    excerpt_title?: string;
    excerpt_context?: Record<string, unknown>;
  },
): Promise<WorkflowResponse> {
  return requestJson("/ingest", {
    method: "POST",
    body: {
      execution: "queued",
      kind: "excerpt",
      ...selectorToBody(selector),
      write: true,
      write_report: true,
      append_ledger: true,
      auto_scoped_lint: true,
      ...body,
    },
  });
}

export async function runLint(body: Record<string, unknown>): Promise<unknown> {
  return requestJson("/lint", { method: "POST", body: { execution: "queued", ...body } });
}
