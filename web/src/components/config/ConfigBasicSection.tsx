import type { ConfigVaultProfile } from "../../api/client";
import { canOpenDesktopPath, canSelectDesktopDirectory, openDesktopPath, selectDesktopDirectory } from "../../desktop/desktopBridge";
import { PathField } from "./ConfigFormControls";
import type { SectionProps } from "./ConfigSectionTypes";

export function ConfigBasicSection({ form, setForm, t }: SectionProps) {
  async function createNewVaultDraft() {
    if (!canSelectDesktopDirectory()) {
      window.alert(t("desktopDirectoryPickerUnavailable"));
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
    const id = uniqueVaultId(vaults, slugifyVaultId(name || baseName));
    const path = result.path;
    setForm({
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

  function activateVault(index: number) {
    const vaults = normalizedVaults(form).map((vault, candidateIndex) => ({ ...vault, active: candidateIndex === index }));
    syncVaults(vaults);
  }

  function removeVault(index: number) {
    const vaults = normalizedVaults(form).filter((_, candidateIndex) => candidateIndex !== index);
    syncVaults(vaults.length ? vaults : [{ id: "default", name: "My Knowledge Base", path: "./vaults/default", active: true }]);
  }

  function syncVaults(vaults: ConfigVaultProfile[]) {
    const active = vaults.find((vault) => vault.active) || vaults[0];
    setForm({
      ...form,
      project_name: active.name,
      vault_path: active.path,
      vault_id: active.id,
      vaults: vaults.map((vault) => ({ ...vault, active: vault.id === active.id })),
    });
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
            <label className="radio-field">
              <input type="radio" checked={vault.active} onChange={() => activateVault(index)} />
              <span>{t("activeVault")}</span>
            </label>
            <label className="field compact-field">
              <span>{t("projectName")}</span>
              <input value={vault.name} onChange={(event) => updateVault(index, { name: event.target.value })} placeholder={t("projectNamePlaceholder")} />
            </label>
            <PathField
              className="compact-field vault-path-field"
              label={t("vaultPath")}
              value={vault.path}
              onChange={(value) => updateVault(index, { path: value })}
              placeholder="./vaults/default"
              selectDirectoryTitle={t("chooseVaultFolder")}
              t={t}
            />
            <div className="vault-profile-actions">
              {canOpenDesktopPath() && (
                <button className="button secondary vault-open-button" type="button" onClick={() => void openVaultFolder(vault.path)}>
                  {t("openVaultFolder")}
                </button>
              )}
              <button className="icon-button" type="button" onClick={() => removeVault(index)} aria-label={t("removeVault")} disabled={normalizedVaults(form).length <= 1}>
                ×
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
    : [{ id: form.vault_id || "default", name: form.project_name || "My Knowledge Base", path: form.vault_path || "./vaults/default", active: true }];
  const activeId = form.vault_id || vaults.find((vault) => vault.active)?.id || vaults[0]?.id;
  return vaults.map((vault) => ({ ...vault, active: vault.id === activeId || Boolean(vault.active && !activeId) }));
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

function slugifyVaultId(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
}
