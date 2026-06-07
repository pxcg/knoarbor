import type { ConfigSummary } from "./api/client";
import type { ReportSummary, UiStatusResponse } from "./api/client";
import type { RunRecord } from "./types";

export type VaultOption = {
  id: string;
  name: string;
  path: string;
};

export type VaultOverview = {
  vault: VaultOption;
  status: UiStatusResponse | null;
  activeRuns: RunRecord[];
  recentRuns: RunRecord[];
  reports: ReportSummary[];
  error?: string | null;
};

export function buildVaultOptions(summary: ConfigSummary): VaultOption[] {
  const configured = summary.vaults?.filter((vault) => vault.id && vault.path) || [];
  if (configured.length) {
    return configured.map((vault) => ({
      id: vault.id,
      name: vault.name || vault.id,
      path: vault.path,
    }));
  }
  return [
    {
      id: summary.vault_id || "default",
      name: summary.vault_name || summary.project_name || "KnoArbor",
      path: summary.vault_path || "./wiki",
    },
  ];
}

export function resolveActiveVault(options: VaultOption[], preferredId: string, summary: ConfigSummary): VaultOption {
  return (
    options.find((vault) => vault.id === preferredId) ||
    options.find((vault) => vault.id === summary.vault_id) ||
    options[0] || {
      id: summary.vault_id || "default",
      name: summary.vault_name || summary.project_name || "KnoArbor",
      path: summary.vault_path || "./wiki",
    }
  );
}

export function nextValidVaultId(options: VaultOption[], preferredId: string, summary: ConfigSummary): string {
  if (options.some((vault) => vault.id === preferredId)) return preferredId;
  return summary.vault_id || options[0]?.id || "default";
}
