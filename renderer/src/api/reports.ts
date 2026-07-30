import { requestJson } from "./http";
import { singleVaultQuery, vaultListQuery, type VaultScopedListOptions } from "./scope";
import type { ReportDetail, ReportSummary, VaultSelector } from "./types";

export async function getReports(
  selector: VaultSelector,
  options: VaultScopedListOptions = {},
): Promise<{ vault_path: string; vault_id?: string | null; vault_name?: string | null; reports: ReportSummary[] }> {
  return requestJson(`/reports?${vaultListQuery(selector, options)}`);
}

export async function getReport(selector: VaultSelector, path: string): Promise<ReportDetail> {
  return requestJson(`/reports/content?${singleVaultQuery(selector)}&path=${encodeURIComponent(path)}`);
}

