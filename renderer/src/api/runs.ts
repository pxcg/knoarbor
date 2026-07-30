import type { RunEvent, RunRecord } from "../types";
import { requestJson } from "./http";
import { singleVaultQuery, vaultListQuery, type VaultScopedListOptions } from "./scope";
import type { VaultSelector } from "./types";

export async function getRuns(selector: VaultSelector, activeOnly = false, limit = 50, options: VaultScopedListOptions = {}): Promise<{ runs: RunRecord[] }> {
  const params = vaultListQuery(selector, options);
  return requestJson(`/runs?${params}&active_only=${activeOnly ? "true" : "false"}&limit=${limit}`);
}

export async function getActiveRuns(selector: VaultSelector): Promise<{ runs: RunRecord[] }> {
  return requestJson(`/runs?${singleVaultQuery(selector)}&active_only=true`);
}

export async function getRun(selector: VaultSelector, runId: string): Promise<RunRecord> {
  return requestJson(`/runs/${encodeURIComponent(runId)}?${singleVaultQuery(selector)}`);
}

export async function getRunEvents(selector: VaultSelector, runId: string, after = 0): Promise<{ events: RunEvent[] }> {
  return requestJson(`/runs/${encodeURIComponent(runId)}/events?${singleVaultQuery(selector)}&after=${after}`);
}

export async function cancelRun(selector: VaultSelector, runId: string): Promise<RunRecord> {
  return requestJson(`/runs/${encodeURIComponent(runId)}/cancel?${singleVaultQuery(selector)}`, { method: "POST" });
}

export async function rerunFailedRun(selector: VaultSelector, runId: string, body: Record<string, unknown> = {}): Promise<unknown> {
  return requestJson("/ingest", {
    method: "POST",
    body: { execution: "queued", kind: "recovery", config_path: selector.config_path, vault_id: selector.vault_id, recovery_vault_path: selector.vault_path, recovery_of_run_id: runId, ...body },
  });
}

export async function rebuildIngestMaterialization(selector: VaultSelector): Promise<unknown> {
  return requestJson(`/ingest/materialization/rebuild?${singleVaultQuery(selector)}`, { method: "POST", body: {} });
}

