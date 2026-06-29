import {
  getActiveRuns,
  getReports,
  getRuns,
  getStatus,
  type ModelProviderProbeState,
} from "./api/client";
import { buildVaultSelector, type VaultOption, type VaultOverview } from "./vaultRuntime";

export async function fetchVaultOverview(vault: VaultOption, configPath: string | null): Promise<VaultOverview> {
  const selector = buildVaultSelector(configPath, vault);
  const [statusResult, activeRunsResult, recentRunsResult, reportsResult] = await Promise.allSettled([
    getStatus(vault.path),
    getActiveRuns(selector),
    getRuns(selector, false, 6),
    getReports(selector),
  ]);
  const error = [statusResult, activeRunsResult, recentRunsResult, reportsResult]
    .find((result) => result.status === "rejected");
  return {
    vault,
    status: statusResult.status === "fulfilled" ? statusResult.value : null,
    activeRuns: activeRunsResult.status === "fulfilled" ? activeRunsResult.value.runs : [],
    recentRuns: recentRunsResult.status === "fulfilled" ? recentRunsResult.value.runs : [],
    reports: reportsResult.status === "fulfilled" ? reportsResult.value.reports : [],
    error: error?.status === "rejected" ? String(error.reason instanceof Error ? error.reason.message : error.reason) : null,
  };
}

export function readStoredModelProbeResults(): Record<string, ModelProviderProbeState> {
  try {
    const raw = localStorage.getItem("knoarbor.modelProbeResults");
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}
