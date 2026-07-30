import type { ConfigSummary, VaultListResponse, VaultSelector } from "./api/client";
import { productIdentity } from "./product";

export type VaultOption = {
  id: string;
  name: string;
  path: string;
  exists?: boolean;
  virtual?: boolean;
};

const LEGACY_DEFAULT_VAULT_NAMES = new Set(["KnoArbor Knowledge Base", "My Knowledge Base", "KnoArbor Knowledge Base"]);

export function readableVaultName(id: string | undefined, name: string | undefined): string {
  const candidate = (name || "").trim();
  if ((id || "").toLowerCase() === "default" && (!candidate || LEGACY_DEFAULT_VAULT_NAMES.has(candidate))) {
    return productIdentity.defaultVaultName;
  }
  return candidate || id || productIdentity.defaultVaultName;
}

export function vaultIdSlug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function buildVaultOptions(summary: ConfigSummary, registry?: VaultListResponse | null): VaultOption[] {
  const registryVaults = registry?.vaults?.filter((vault) => vault.id && vault.path) || [];
  if (registryVaults.length) {
    return withVirtualAllVault(registryVaults.map((vault) => ({
      id: vault.id,
      name: readableVaultName(vault.id, vault.name),
      path: vault.path,
      exists: vault.exists,
    })));
  }
  const configured = summary.vaults?.filter((vault) => vault.id && vault.path) || [];
  if (configured.length) {
    return withVirtualAllVault(configured.map((vault) => ({
      id: vault.id,
      name: readableVaultName(vault.id, vault.name),
      path: vault.path,
    })));
  }
  return [
    {
      id: summary.vault_id || "default",
      name: readableVaultName(summary.vault_id || "default", summary.vault_name || summary.project_name),
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
      name: readableVaultName(summary.vault_id || "default", summary.vault_name || summary.project_name),
      path: summary.vault_path || "./vaults/default",
    }
  );
}

export function nextValidWorkspaceVaultId(options: VaultOption[], preferredId: string, summary: ConfigSummary): string {
  const concrete = concreteVaultOptions(options);
  if (concrete.some((vault) => vault.id === preferredId)) return preferredId;
  return concrete.find((vault) => vault.id === summary.vault_id)?.id || concrete[0]?.id || "default";
}

export function nextValidChatScopeVaultId(options: VaultOption[], preferredId: string, workspaceVaultId: string): string {
  if (options.some((vault) => vault.id === preferredId)) return preferredId;
  return options.find((vault) => vault.id === "all")?.id || workspaceVaultId || options[0]?.id || "default";
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
