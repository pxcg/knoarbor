import { ingestExcerpt, type VaultSelector, type WorkflowResponse } from "../api/client";
import type { ExcerptIngestAppContext } from "../appContext";

export type ExcerptIngestDraft = {
  content: string;
  context: Record<string, unknown>;
  title: string;
  targetVaultId: string;
};

export function defaultExcerptTargetVaultId(context: ExcerptIngestAppContext, preferredVaultId?: string): string {
  const vaults = context.vaultOptions.filter((vault) => !vault.virtual);
  if (preferredVaultId && vaults.some((vault) => vault.id === preferredVaultId)) return preferredVaultId;
  if (context.activeVaultId !== "all" && vaults.some((vault) => vault.id === context.activeVaultId)) {
    return context.activeVaultId;
  }
  return vaults[0]?.id || "";
}

export function excerptDraftIsValid(draft: ExcerptIngestDraft | null): draft is ExcerptIngestDraft {
  return Boolean(draft?.title.trim() && draft.content.trim() && draft.targetVaultId);
}

export function submitExcerptDraft(configPath: VaultSelector["config_path"], draft: ExcerptIngestDraft): Promise<WorkflowResponse> {
  const selector: VaultSelector = {
    config_path: configPath,
    vault_id: draft.targetVaultId,
  };
  return ingestExcerpt(selector, {
    excerpt_text: draft.content.trim(),
    excerpt_title: draft.title.trim(),
    excerpt_context: draft.context,
  });
}

