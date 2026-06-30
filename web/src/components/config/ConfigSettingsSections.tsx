import type { Dispatch, SetStateAction } from "react";
import { useState } from "react";

import type { ConfigForm, ConfigVaultProfile } from "../../api/client";
import { BrandIcon, type BrandIconName } from "../BrandIcon";
import { ConnectorCard, PathField, splitLines } from "./ConfigFormControls";

type SectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
};

export function ConfigBasicSection({ form, setForm, t }: SectionProps) {
  async function createNewVaultDraft() {
    if (!window.knoarborDesktop?.selectDirectory) {
      window.alert(t("desktopDirectoryPickerUnavailable"));
      return;
    }
    const result = await window.knoarborDesktop.selectDirectory({
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
              {window.knoarborDesktop?.openPath && (
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

function normalizedVaults(form: ConfigForm): ConfigVaultProfile[] {
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
  if (!path || !window.knoarborDesktop?.openPath) return;
  await window.knoarborDesktop.openPath(path);
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

export function ConfigRuntimeSection({ form, setForm, t }: SectionProps) {
  return (
    <>
      <div className="section-divider" id="settings-runtime">
        <div>
          <h2>{t("runtimeParameters")}</h2>
          <p className="panel-copy">{t("runtimeParametersCopy")}</p>
        </div>
      </div>
      <div className="form-grid config-runtime-grid">
        <label className="field">
          <span>{t("serverHost")}</span>
          <input value={form.server_host} onChange={(event) => setForm({ ...form, server_host: event.target.value })} />
        </label>
        <label className="field">
          <span>{t("serverPort")}</span>
          <input type="number" value={form.server_port} onChange={(event) => setForm({ ...form, server_port: Number(event.target.value) })} />
        </label>
        <label className="field">
          <span>{t("defaultProvider")}</span>
          <select value={form.default_provider} onChange={(event) => setForm({ ...form, default_provider: event.target.value })}>
            <option value="">{t("none")}</option>
            {form.providers
              .filter((provider) => provider.name)
              .map((provider) => (
                <option value={provider.name} key={provider.name}>
                  {provider.name}
                </option>
              ))}
          </select>
        </label>
        <label className="field">
          <span>{t("maxTokens")}</span>
          <input
            type="number"
            value={form.default_max_tokens || ""}
            onChange={(event) => setForm({ ...form, default_max_tokens: event.target.value ? Number(event.target.value) : null })}
          />
        </label>
        <label className="field">
          <span>{t("requestTimeout")}</span>
          <input type="number" value={form.request_timeout_seconds} onChange={(event) => setForm({ ...form, request_timeout_seconds: Number(event.target.value) })} />
        </label>
      </div>
    </>
  );
}

export function ConfigInputsSection({ form, setForm, t }: SectionProps) {
  const genericChatRoots = form.generic_chat_roots || [];
  const chatSources: ChatSourceRow[] = [
    {
      key: "codex",
      icon: "codex",
      title: t("codexConnector"),
      enabled: form.codex_enabled,
      path: form.codex_sessions_dir,
      setEnabled: (checked) => setForm({ ...form, codex_enabled: checked }),
      setPath: (value) => setForm({ ...form, codex_sessions_dir: value }),
      placeholder: "~/.codex/sessions",
    },
    {
      key: "hermes",
      icon: "hermes",
      title: t("hermesConnector"),
      enabled: form.hermes_enabled,
      path: form.hermes_sessions_dir,
      setEnabled: (checked) => setForm({ ...form, hermes_enabled: checked }),
      setPath: (value) => setForm({ ...form, hermes_sessions_dir: value }),
      placeholder: "~/.hermes/sessions",
    },
    {
      key: "openclaw",
      icon: "openclaw",
      title: t("openclawConnector"),
      enabled: form.openclaw_enabled,
      path: form.openclaw_sessions_dir,
      setEnabled: (checked) => setForm({ ...form, openclaw_enabled: checked }),
      setPath: (value) => setForm({ ...form, openclaw_sessions_dir: value }),
      placeholder: "~/.openclaw/agents/main/sessions",
    },
    {
      key: "claude_code",
      icon: "claude_code",
      title: t("claudeCodeConnector"),
      enabled: form.claude_code_enabled,
      path: form.claude_code_sessions_dir,
      setEnabled: (checked) => setForm({ ...form, claude_code_enabled: checked }),
      setPath: (value) => setForm({ ...form, claude_code_sessions_dir: value }),
      placeholder: "~/.claude/projects",
    },
  ];

  return (
    <>
      <div className="section-divider" id="settings-inputs">
        <div>
          <h2>{t("inputPaths")}</h2>
          <p className="panel-copy">{t("inputPathsCopy")}</p>
        </div>
      </div>
      <div className="settings-card-grid">
        <ConnectorCard title={t("markdownConnector")} checked={form.markdown_enabled} onChange={(checked) => setForm({ ...form, markdown_enabled: checked })}>
          <label className="field">
            <span>{t("markdownRoots")}</span>
            <textarea className="path-list-editor" value={form.markdown_roots.join("\n")} onChange={(event) => setForm({ ...form, markdown_roots: splitLines(event.target.value) })} />
          </label>
        </ConnectorCard>
        <ConnectorCard title={t("nonMarkdownConnector")} checked={form.mineru_enabled} onChange={(checked) => setForm({ ...form, mineru_enabled: checked })}>
          <PathField label={t("nonMarkdownInputDir")} value={form.mineru_input_dir} onChange={(value) => setForm({ ...form, mineru_input_dir: value })} placeholder="./vaults/all/raw/inbox/documents" selectDirectoryTitle={t("chooseSourceFolder")} t={t} />
          <p className="panel-copy compact-copy">{t("nonMarkdownInputCopy")}</p>
        </ConnectorCard>
        <section className="settings-subcard chat-source-card">
          <div>
            <h3>{t("chatRecordInputs")}</h3>
            <p className="panel-copy">{t("chatRecordInputsCopy")}</p>
          </div>
          <div className="chat-source-list">
            {chatSources.map((source) => (
              <ChatSourceField key={source.key} source={source} t={t} />
            ))}
            <div className="chat-source-row custom">
              <label className="checkbox-field compact chat-source-toggle">
                <input type="checkbox" checked={form.generic_chat_enabled} onChange={(event) => setForm({ ...form, generic_chat_enabled: event.target.checked })} />
                <span className="chat-source-label">
                  <span className="chat-source-icon">
                    <BrandIcon name="generic_chat" />
                  </span>
                  {t("genericChatConnector")}
                </span>
              </label>
              <label className="field chat-source-path">
                <textarea
                  className="path-list-editor compact"
                  value={genericChatRoots.join("\n")}
                  onChange={(event) => setForm({ ...form, generic_chat_roots: splitLines(event.target.value) })}
                  placeholder={t("genericChatRootsPlaceholder")}
                  aria-label={t("genericChatRoots")}
                />
              </label>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

type ChatSourceRow = {
  key: string;
  icon: BrandIconName;
  title: string;
  enabled: boolean;
  path: string;
  setEnabled: (checked: boolean) => void;
  setPath: (value: string) => void;
  placeholder: string;
};

function ChatSourceField({ source, t }: { source: ChatSourceRow; t: (key: string) => string }) {
  return (
    <div className="chat-source-row">
      <label className="checkbox-field compact chat-source-toggle">
        <input type="checkbox" checked={source.enabled} onChange={(event) => source.setEnabled(event.target.checked)} />
        <span className="chat-source-label">
          <span className="chat-source-icon">
            <BrandIcon name={source.icon} />
          </span>
          {source.title}
        </span>
      </label>
      <PathField label="" value={source.path} onChange={source.setPath} className="chat-source-path" placeholder={source.placeholder} ariaLabel={source.title} selectDirectoryTitle={source.title} t={t} />
    </div>
  );
}

export function ConfigPreprocessingSection({ form, setForm, t }: SectionProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const returnFields = [
    ["mineru_return_md", "mineruReturnMd"],
    ["mineru_return_middle_json", "mineruReturnMiddleJson"],
    ["mineru_return_model_output", "mineruReturnModelOutput"],
    ["mineru_return_content_list", "mineruReturnContentList"],
    ["mineru_return_images", "mineruReturnImages"],
    ["mineru_response_format_zip", "mineruResponseFormatZip"],
    ["mineru_formula_enable", "mineruFormulaEnable"],
    ["mineru_table_enable", "mineruTableEnable"],
  ] as const;

  function updateMinerUBoolean(key: (typeof returnFields)[number][0], checked: boolean) {
    setForm({ ...form, [key]: checked });
  }

  return (
    <>
      <div className="section-divider" id="settings-preprocessing">
        <div>
          <h2>{t("documentPreprocessing")}</h2>
          <p className="panel-copy">{t("documentPreprocessingCopy")}</p>
        </div>
      </div>
      <div className="settings-card-grid single">
        <section className="settings-subcard">
          <div className="settings-subcard-header">
            <h3>MinerU Adapter</h3>
            <button className="button secondary small-button" type="button" onClick={() => setAdvancedOpen(!advancedOpen)}>
              {advancedOpen ? t("hideAdvanced") : t("showAdvanced")}
            </button>
          </div>
          <label className="checkbox-field compact">
            <input type="checkbox" checked={form.mineru_enabled} onChange={(event) => setForm({ ...form, mineru_enabled: event.target.checked })} />
            <span>{t("nonMarkdownConnector")}</span>
          </label>
          <PathField label={t("mineruEndpoint")} value={form.mineru_endpoint} onChange={(value) => setForm({ ...form, mineru_endpoint: value })} placeholder="http://127.0.0.1:18000/file_parse" />
          {advancedOpen && (
            <div className="advanced-config-panel">
              <div className="form-grid settings-path-grid">
                <label className="field">
                  <span>{t("mineruBackend")}</span>
                  <select value={form.mineru_backend} onChange={(event) => setForm({ ...form, mineru_backend: event.target.value })}>
                    <option value="pipeline">pipeline</option>
                    <option value="vlm-engine">vlm-engine</option>
                    <option value="hybrid-engine">hybrid-engine</option>
                    <option value="vlm-http-client">vlm-http-client</option>
                    <option value="hybrid-http-client">hybrid-http-client</option>
                  </select>
                </label>
                <label className="field">
                  <span>{t("mineruParseMethod")}</span>
                  <select value={form.mineru_parse_method} onChange={(event) => setForm({ ...form, mineru_parse_method: event.target.value })}>
                    <option value="auto">auto</option>
                    <option value="txt">txt</option>
                    <option value="ocr">ocr</option>
                  </select>
                </label>
                <label className="field">
                  <span>{t("mineruTimeout")}</span>
                  <input type="number" value={form.mineru_timeout_seconds} onChange={(event) => setForm({ ...form, mineru_timeout_seconds: Number(event.target.value) })} />
                </label>
                <PathField label={t("mineruLangList")} value={form.mineru_lang_list} onChange={(value) => setForm({ ...form, mineru_lang_list: value })} />
                <PathField label={t("mineruServerUrl")} value={form.mineru_server_url} onChange={(value) => setForm({ ...form, mineru_server_url: value })} placeholder={t("optional")} />
                <label className="field">
                  <span>{t("mineruStartPage")}</span>
                  <input type="number" value={form.mineru_start_page_id} onChange={(event) => setForm({ ...form, mineru_start_page_id: Number(event.target.value) })} />
                </label>
                <label className="field">
                  <span>{t("mineruEndPage")}</span>
                  <input type="number" value={form.mineru_end_page_id} onChange={(event) => setForm({ ...form, mineru_end_page_id: Number(event.target.value) })} />
                </label>
              </div>
              <label className="field">
                <span>{t("mineruPatterns")}</span>
                <textarea className="path-list-editor compact" value={form.mineru_patterns.join("\n")} onChange={(event) => setForm({ ...form, mineru_patterns: splitLines(event.target.value) })} />
              </label>
              <div className="checkbox-grid compact-checkbox-grid">
                <label className="checkbox-field compact">
                  <input type="checkbox" checked={form.mineru_recursive} onChange={(event) => setForm({ ...form, mineru_recursive: event.target.checked })} />
                  <span>{t("mineruRecursive")}</span>
                </label>
                {returnFields.map(([key, label]) => (
                  <label className="checkbox-field compact" key={key}>
                    <input type="checkbox" checked={Boolean(form[key])} onChange={(event) => updateMinerUBoolean(key, event.target.checked)} />
                    <span>{t(label)}</span>
                  </label>
                ))}
              </div>
              <label className="field">
                <span>{t("mineruExtraFields")}</span>
                <textarea className="config-editor compact-json-editor" value={form.mineru_extra_fields_json} onChange={(event) => setForm({ ...form, mineru_extra_fields_json: event.target.value })} spellCheck={false} />
              </label>
              <p className="panel-copy compact-copy">{t("mineruAdvancedCopy")}</p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
