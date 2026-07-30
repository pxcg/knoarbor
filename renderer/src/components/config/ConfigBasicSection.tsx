import { useState } from "react";

import type { ConfigForm, ConfigVaultProfile } from "../../api/client";
import { canOpenDesktopPath, canSelectDesktopDirectory, openDesktopPath, selectDesktopDirectory } from "../../desktop/desktopBridge";
import { productIdentity } from "../../product";
import { readableVaultName, vaultIdSlug } from "../../vaultRuntime";
import type { SectionProps } from "./ConfigSectionTypes";

type ConfigBasicSectionProps = SectionProps & {
  onCommit: (nextForm: ConfigForm) => Promise<void>;
  onError: (error: unknown) => void;
};

export function ConfigBasicSection({ form, setForm, t, onCommit, onError }: ConfigBasicSectionProps) {
  const [removingVaultIndex, setRemovingVaultIndex] = useState<number | null>(null);

  async function commit(nextForm: ConfigForm) {
    const previousForm = form;
    setForm(nextForm);
    try {
      await onCommit(nextForm);
    } catch (error) {
      setForm((current) => current === nextForm ? previousForm : current);
      onError(error);
    }
  }

  async function createNewVaultDraft() {
    if (!canSelectDesktopDirectory()) {
      onError(new Error(t("desktopDirectoryPickerUnavailable")));
      return;
    }
    const result = await selectDesktopDirectory({
      defaultPath: form.vault_path || "./vaults/default",
      title: t("chooseVaultFolder"),
    });
    if (result.canceled || !result.path) return;

    const vaults = normalizedVaults(form);
    const baseName = vaultNameFromPath(result.path) || t("newVaultDefaultName");
    const name = uniqueVaultName(vaults, baseName);
    const id = uniqueVaultId(vaults, vaultIdSlug(name || baseName));
    const path = result.path;
    await commit({
      ...form,
      project_name: name,
      vault_path: path,
      vault_id: id,
      vaults: [...vaults.map((vault) => ({ ...vault, active: false })), { id, name, path, active: true }],
    });
  }

  function updateVault(index: number, patch: Partial<ConfigVaultProfile>) {
    const vaults = normalizedVaults(form).map((vault, candidateIndex) => (candidateIndex === index ? { ...vault, ...patch } : vault));
    syncVaults(vaults);
  }

  async function removeVault(index: number) {
    const vaults = normalizedVaults(form);
    const target = vaults[index];
    if (!target || vaults.length <= 1 || removingVaultIndex !== null) return;
    const confirmed = window.confirm(t("removeVaultConfirm").replace("{name}", target.name).replace("{path}", target.path));
    if (!confirmed) return;

    const nextVaults = vaults.filter((_, candidateIndex) => candidateIndex !== index);
    const nextForm = syncedVaultForm(nextVaults);
    setRemovingVaultIndex(index);
    try {
      await commit(nextForm);
    } finally {
      setRemovingVaultIndex(null);
    }
  }

  function syncVaults(vaults: ConfigVaultProfile[]) {
    setForm(syncedVaultForm(vaults));
  }

  function commitCurrentForm() {
    void commit(form);
  }

  function syncedVaultForm(vaults: ConfigVaultProfile[]): ConfigForm {
    const active = vaults.find((vault) => vault.active) || vaults[0];
    return {
      ...form,
      project_name: active.name,
      vault_path: active.path,
      vault_id: active.id,
      vaults: vaults.map((vault) => ({ ...vault, active: vault.id === active.id })),
    };
  }

  return (
    <>
      <div className="settings-inline-action">
        <div>
          <h3>{t("knowledgeBaseProfile")}</h3>
          <p className="panel-copy">{t("knowledgeBaseProfileCopy")}</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void createNewVaultDraft()}>
          {t("newVault")}
        </button>
      </div>
      <div className="vault-profile-list" id="settings-basic">
        {normalizedVaults(form).map((vault, index) => (
          <div className={`vault-profile-row ${vault.active ? "active" : ""}`} key={`${vault.id}-${index}`}>
            <label className="field compact-field vault-name-field">
              <span>{t("projectName")}</span>
              <input value={vault.name} onBlur={commitCurrentForm} onChange={(event) => updateVault(index, { name: event.target.value })} placeholder={t("projectNamePlaceholder")} />
            </label>
            <label className="field compact-field vault-path-field">
              <span>{t("vaultPath")}</span>
              <input value={vault.path} onBlur={commitCurrentForm} onChange={(event) => updateVault(index, { path: event.target.value })} placeholder="./vaults/default" />
            </label>
            <div className="vault-profile-actions">
              {canOpenDesktopPath() && (
                <button className="button secondary vault-open-button" type="button" onClick={() => void openVaultFolder(vault.path)}>
                  {t("openVaultFolder")}
                </button>
              )}
              <button className="icon-button vault-remove-button" type="button" onClick={() => void removeVault(index)} aria-label={t("removeVault")} disabled={normalizedVaults(form).length <= 1 || removingVaultIndex !== null}>
                {removingVaultIndex === index ? "…" : "×"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function normalizedVaults(form: SectionProps["form"]): ConfigVaultProfile[] {
  const vaults = form.vaults?.length
    ? form.vaults
    : [{ id: form.vault_id || "default", name: form.project_name || productIdentity.defaultVaultName, path: form.vault_path || "./vaults/default", active: true }];
  const activeId = form.vault_id || vaults.find((vault) => vault.active)?.id || vaults[0]?.id;
  return vaults.map((vault) => ({
    ...vault,
    name: readableVaultName(vault.id, vault.name),
    active: vault.id === activeId || Boolean(vault.active && !activeId),
  }));
}

function vaultNameFromPath(path: string): string {
  const normalized = path.replace(/[\\/]+$/, "");
  const parts = normalized.split(/[\\/]/).filter(Boolean);
  const name = parts.length ? parts[parts.length - 1] : "";
  return name.trim();
}

async function openVaultFolder(path: string) {
  await openDesktopPath(path);
}

function uniqueVaultId(vaults: ConfigVaultProfile[], baseId: string): string {
  const used = new Set(vaults.map((vault) => vault.id));
  const fallback = baseId || "vault";
  if (!used.has(fallback)) return fallback;
  let suffix = 2;
  while (used.has(`${fallback}-${suffix}`)) suffix += 1;
  return `${fallback}-${suffix}`;
}

function uniqueVaultName(vaults: ConfigVaultProfile[], baseName: string): string {
  const used = new Set(vaults.map((vault) => vault.name));
  if (!used.has(baseName)) return baseName;
  let suffix = 2;
  while (used.has(`${baseName} ${suffix}`)) suffix += 1;
  return `${baseName} ${suffix}`;
}
