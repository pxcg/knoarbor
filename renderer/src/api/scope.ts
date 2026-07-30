import type { VaultSelector } from "./types";

export type VaultScopedListOptions = {
  config_path?: string | null;
  vault_id?: string | null;
  vault_ids?: string[];
  all_vaults?: boolean;
};

export function selectorToBody(selector: VaultSelector): Record<string, unknown> {
  return {
    config_path: selector.config_path ?? undefined,
    vault_id: selector.vault_id ?? undefined,
    vault_path: selector.vault_id ? undefined : selector.vault_path ?? undefined,
  };
}

export function singleVaultQuery(selector: VaultSelector): string {
  const params = new URLSearchParams();
  if (selector.config_path) params.set("config_path", selector.config_path);
  if (selector.vault_id) params.set("vault_id", selector.vault_id);
  if (!selector.vault_id && selector.vault_path) params.set("vault_path", selector.vault_path);
  return params.toString();
}

export function vaultListQuery(selector: VaultSelector, options: VaultScopedListOptions = {}): string {
  const params = new URLSearchParams();
  const configPath = options.config_path ?? selector.config_path;
  if (configPath) params.set("config_path", configPath);
  if (options.vault_id) {
    params.set("vault_id", options.vault_id);
  } else if (selector.vault_id && !options.all_vaults && !options.vault_ids?.length) {
    params.set("vault_id", selector.vault_id);
  } else if (!options.all_vaults && !options.vault_ids?.length && selector.vault_path) {
    params.set("vault_path", selector.vault_path);
  }
  if (options.all_vaults) params.set("all_vaults", "true");
  for (const vaultId of options.vault_ids || []) params.append("vault_ids", vaultId);
  return params.toString();
}
