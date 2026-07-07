import type { ConfigSummary, VaultListResponse, VaultSelector } from "./api/client";
import type { ReportSummary, UiStatusResponse } from "./api/client";
import type { RunRecord } from "./types";

export type VaultOption = {
  id: string;
  name: string;
  path: string;
  exists?: boolean;
  virtual?: boolean;
};

export type VaultOverview = {
  vault: VaultOption;
  status: UiStatusResponse | null;
  activeRuns: RunRecord[];
  recentRuns: RunRecord[];
  reports: ReportSummary[];
  error?: string | null;
};

export function buildVaultOptions(summary: ConfigSummary, registry?: VaultListResponse | null): VaultOption[] {
  const registryVaults = registry?.vaults?.filter((vault) => vault.id && vault.path) || [];
  if (registryVaults.length) {
    return withVirtualAllVault(registryVaults.map((vault) => ({
      id: vault.id,
      name: vault.name || vault.id,
      path: vault.path,
      exists: vault.exists,
    })));
  }
  const configured = summary.vaults?.filter((vault) => vault.id && vault.path) || [];
  if (configured.length) {
    return withVirtualAllVault(configured.map((vault) => ({
      id: vault.id,
      name: vault.name || vault.id,
      path: vault.path,
    })));
  }
  return [
    {
      id: summary.vault_id || "default",
      name: summary.vault_name || summary.project_name || "KnoArbor",
      path: summary.vault_path || "./vaults/default",
    },
  ];
}

export function resolveActiveVault(options: VaultOption[], preferredId: string, summary: ConfigSummary): VaultOption {
  return (
    options.find((vault) => vault.id === preferredId) ||
    (!preferredId ? options.find((vault) => vault.id === "all") : undefined) ||
    options.find((vault) => vault.id === summary.vault_id) ||
    options[0] || {
      id: summary.vault_id || "default",
      name: summary.vault_name || summary.project_name || "KnoArbor",
      path: summary.vault_path || "./vaults/default",
    }
  );
}

export function nextValidVaultId(options: VaultOption[], preferredId: string, summary: ConfigSummary): string {
  if (options.some((vault) => vault.id === preferredId)) return preferredId;
  if (!preferredId) return options.find((vault) => vault.id === "all")?.id || summary.vault_id || options[0]?.id || "default";
  return summary.vault_id || options[0]?.id || "default";
}

export function buildVaultSelector(configPath: string | null, vault: VaultOption): VaultSelector {
  if (vault.virtual) {
    return {
      config_path: configPath,
      vault_id: vault.id,
    };
  }
  return {
    config_path: configPath,
    vault_id: vault.id,
    vault_path: vault.path,
  };
}

export function concreteVaultOptions(options: VaultOption[]): VaultOption[] {
  return options.filter((vault) => !vault.virtual);
}

export function readableVaultName(id: string, name?: string): string {
  if (name?.trim()) return name.trim();
  if (id === "all") return "All vaults";
  return id || "KnoArbor";
}

export function resolveConcreteVault(options: VaultOption[], preferredId: string, summary: ConfigSummary): VaultOption {
  return resolveActiveVault(concreteVaultOptions(options), preferredId === "all" ? "" : preferredId, summary);
}

function withVirtualAllVault(options: VaultOption[]): VaultOption[] {
  const concrete = options.filter((vault) => vault.id !== "all");
  if (concrete.length <= 1) return concrete;
  return [
    {
      id: "all",
      name: "All vaults",
      path: "",
      virtual: true,
      exists: true,
    },
    ...concrete,
  ];
}
