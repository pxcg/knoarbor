import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useState } from "react";

import type { ConfigForm, ConfigFormProvider, ConfigVaultProfile, ModelCapabilitySuggestion, ModelProviderProbeState } from "../../api/client";
import { BrandIcon, type BrandIconName } from "../BrandIcon";

type SectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
};

type ProviderRuntimeStatus = {
  tone: "ok" | "warning" | "error" | "unknown";
  dotClass: "online" | "warning" | "offline" | "neutral";
  label: string;
  detail: string;
  checked: boolean;
};

const PROVIDER_PRESETS: ConfigFormProvider[] = [
  {
    name: "deepseek",
    adapter: "openai_compatible",
    base_url: "https://api.deepseek.com",
    api_key_env: "DEEPSEEK_API_KEY",
    model: "deepseek-v4-flash",
    json_mode: true,
    verify_tls: true,
    tls_ca_file: "",
    context_window: null,
    max_output_tokens: null,
    api_key_configured: false,
  },
  {
    name: "openai",
    adapter: "openai_compatible",
    base_url: "https://api.openai.com/v1",
    api_key_env: "OPENAI_API_KEY",
    model: "gpt-4.1",
    json_mode: true,
    verify_tls: true,
    tls_ca_file: "",
    context_window: null,
    max_output_tokens: null,
    api_key_configured: false,
  },
  {
    name: "vllm",
    adapter: "openai_compatible",
    base_url: "http://localhost:8001/v1",
    api_key_env: "",
    model: "local-model",
    json_mode: true,
    verify_tls: true,
    tls_ca_file: "",
    context_window: 32768,
    max_output_tokens: 8000,
    api_key_configured: true,
  },
  {
    name: "ollama",
    adapter: "ollama",
    base_url: "http://localhost:11434",
    api_key_env: "",
    model: "qwen3.6:27b-q4_K_M",
    json_mode: true,
    verify_tls: true,
    tls_ca_file: "",
    context_window: 262144,
    max_output_tokens: 8000,
    extra_body: { think: false },
    api_key_configured: true,
  },
];

export function ConfigBasicSection({ form, setForm, t }: SectionProps) {
  function createNewVaultDraft() {
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    const id = `vault-${stamp}`;
    const vaults = normalizedVaults(form);
    setForm({
      ...form,
      project_name: `${t("newVaultDefaultName")} ${stamp}`,
      vault_path: `./vaults/${id}`,
      vault_id: id,
      vaults: [...vaults.map((vault) => ({ ...vault, active: false })), { id, name: `${t("newVaultDefaultName")} ${stamp}`, path: `./vaults/${id}`, active: true }],
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
    syncVaults(vaults.length ? vaults : [{ id: "all", name: "My Knowledge Base", path: "./vaults/all", active: true }]);
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
        <button className="button secondary" type="button" onClick={createNewVaultDraft}>
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
              <span>{t("vaultId")}</span>
              <input value={vault.id} onChange={(event) => updateVault(index, { id: event.target.value })} placeholder="personal" />
            </label>
            <label className="field compact-field">
              <span>{t("projectName")}</span>
              <input value={vault.name} onChange={(event) => updateVault(index, { name: event.target.value })} placeholder={t("projectNamePlaceholder")} />
            </label>
            <label className="field compact-field vault-path-field">
              <span>{t("vaultPath")}</span>
              <input value={vault.path} onChange={(event) => updateVault(index, { path: event.target.value })} placeholder="./vaults/all" />
            </label>
            <button className="icon-button" type="button" onClick={() => removeVault(index)} aria-label={t("removeVault")} disabled={normalizedVaults(form).length <= 1}>
              ×
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

function normalizedVaults(form: ConfigForm): ConfigVaultProfile[] {
  const vaults = form.vaults?.length
    ? form.vaults
    : [{ id: form.vault_id || "all", name: form.project_name || "My Knowledge Base", path: form.vault_path || "./vaults/all", active: true }];
  const activeId = form.vault_id || vaults.find((vault) => vault.active)?.id || vaults[0]?.id;
  return vaults.map((vault) => ({ ...vault, active: vault.id === activeId || Boolean(vault.active && !activeId) }));
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
          <PathField label={t("nonMarkdownInputDir")} value={form.mineru_input_dir} onChange={(value) => setForm({ ...form, mineru_input_dir: value })} placeholder="./vaults/all/raw/documents/originals" />
          <p className="panel-copy compact-copy">{t("nonMarkdownInputCopy")}</p>
        </ConnectorCard>
        <section className="settings-subcard chat-source-card">
          <div>
            <h3>{t("chatRecordInputs")}</h3>
            <p className="panel-copy">{t("chatRecordInputsCopy")}</p>
          </div>
          <div className="chat-source-list">
            {chatSources.map((source) => (
              <ChatSourceField key={source.key} source={source} />
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

function ChatSourceField({ source }: { source: ChatSourceRow }) {
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
      <PathField label="" value={source.path} onChange={source.setPath} className="chat-source-path" placeholder={source.placeholder} ariaLabel={source.title} />
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
          <PathField label={t("mineruEndpoint")} value={form.mineru_endpoint} onChange={(value) => setForm({ ...form, mineru_endpoint: value })} placeholder="http://127.0.0.1:18000/file_parse" />
          {advancedOpen && (
            <div className="advanced-config-panel">
              <div className="form-grid settings-path-grid">
                <label className="field">
                  <span>{t("mineruBackend")}</span>
                  <select value={form.mineru_backend} onChange={(event) => setForm({ ...form, mineru_backend: event.target.value })}>
                    <option value="pipeline">pipeline</option>
                    <option value="vlm-auto-engine">vlm-auto-engine</option>
                    <option value="hybrid-auto-engine">hybrid-auto-engine</option>
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

export function ConfigModelProvidersSection({
  form,
  setForm,
  t,
  probeResults,
  pendingAction,
  onDiscover,
  onProbe,
  onApplyCapabilities,
}: SectionProps & {
  probeResults: Record<string, ModelProviderProbeState>;
  pendingAction: string | null;
  onDiscover: (provider: string) => void;
  onProbe: (provider: string, level: "minimal" | "structured") => void;
  onApplyCapabilities: (provider: string, values: ModelCapabilitySuggestion) => void;
}) {
  const [activeProvider, setActiveProvider] = useState(0);
  const [providerPreset, setProviderPreset] = useState(PROVIDER_PRESETS[0].name);

  function updateProvider(index: number, patch: Partial<ConfigFormProvider>) {
    setForm({
      ...form,
      providers: form.providers.map((provider, current) => (current === index ? { ...provider, ...patch } : provider)),
    });
  }

  function addProvider() {
    const preset = PROVIDER_PRESETS.find((item) => item.name === providerPreset);
    const template = preset || {
      name: "",
      base_url: "",
      adapter: "openai_compatible",
      api_key_env: "",
      model: "",
      json_mode: true,
      verify_tls: true,
      tls_ca_file: "",
      context_window: null,
      max_output_tokens: null,
      extra_body: {},
      api_key_configured: false,
    };
    const existingNames = new Set(form.providers.map((provider) => provider.name));
    let name = template.name;
    if (name && existingNames.has(name)) {
      let suffix = 2;
      while (existingNames.has(`${name}-${suffix}`)) suffix += 1;
      name = `${name}-${suffix}`;
    }
    const nextProviders = [...form.providers, { ...template, name }];
    setForm({ ...form, providers: nextProviders, default_provider: form.default_provider || name });
    setActiveProvider(nextProviders.length - 1);
  }

  function removeProvider(index: number) {
    const removedName = form.providers[index]?.name;
    const nextProviders = form.providers.filter((_, current) => current !== index);
    setForm({
      ...form,
      providers: nextProviders,
      default_provider: form.default_provider === removedName ? nextProviders[0]?.name || "" : form.default_provider,
    });
    setActiveProvider(Math.min(index, Math.max(0, nextProviders.length - 1)));
  }

  const active = form.providers[activeProvider];
  const activeRuntimeStatus = active ? providerRuntimeStatus(active, probeResults[active.name], t) : null;
  return (
    <>
      <div className="settings-inline-action model-provider-toolbar" id="settings-models">
        <div>
          <h2>{t("modelProviders")}</h2>
          <p className="panel-copy">{t("modelProvidersCopy")}</p>
        </div>
        <div className="add-provider-control">
          <select value={providerPreset} onChange={(event) => setProviderPreset(event.target.value)} aria-label={t("providerPreset")}>
            {PROVIDER_PRESETS.map((preset) => (
              <option value={preset.name} key={preset.name}>
                {preset.name}
              </option>
            ))}
            <option value="">{t("custom")}</option>
          </select>
          <button className="button secondary" onClick={addProvider} type="button">
            {t("addProvider")}
          </button>
        </div>
      </div>
      <div className="provider-workspace">
        <div className="provider-list">
          {form.providers.map((provider, index) => {
            const runtimeStatus = providerRuntimeStatus(provider, probeResults[provider.name], t);
            return (
              <button className={`provider-row ${index === activeProvider ? "active" : ""} ${runtimeStatus.tone}`} key={`${provider.name}:${index}`} onClick={() => setActiveProvider(index)} type="button">
                <span className={`status-dot ${runtimeStatus.dotClass}`} />
                <strong>{provider.name || t("untitledProvider")}</strong>
                <small title={runtimeStatus.detail}>{runtimeStatus.checked ? `${runtimeStatus.label} · ${runtimeStatus.detail}` : runtimeStatus.detail}</small>
              </button>
            );
          })}
          {!form.providers.length && <div className="empty-state">{t("noProviders")}</div>}
        </div>

        {active && activeRuntimeStatus && (
          <div className={`provider-card ${activeRuntimeStatus.tone}`}>
            <div className="provider-card-header">
              <div>
                <h3>{active.name || t("newProvider")}</h3>
                <p className="panel-copy">{t("providerCopy")}</p>
              </div>
              <div className={`provider-status ${activeRuntimeStatus.tone}`} title={activeRuntimeStatus.detail}>
                <span className={`status-dot ${activeRuntimeStatus.dotClass}`} />
                <span>{activeRuntimeStatus.label}</span>
              </div>
            </div>
            <p className={`provider-status-message ${activeRuntimeStatus.tone}`}>{activeRuntimeStatus.detail}</p>
            <div className="form-grid provider-form-grid">
              <PathField label={t("name")} value={active.name} onChange={(value) => updateProvider(activeProvider, { name: value })} />
              <label className="field">
                <span>{t("modelAdapter")}</span>
                <select value={active.adapter || "openai_compatible"} onChange={(event) => updateProvider(activeProvider, { adapter: event.target.value as ConfigFormProvider["adapter"] })}>
                  <option value="openai_compatible">{t("adapterOpenAICompatible")}</option>
                  <option value="ollama">{t("adapterOllamaNative")}</option>
                </select>
              </label>
              <PathField label={t("model")} value={active.model} onChange={(value) => updateProvider(activeProvider, { model: value })} />
              <PathField label={t("baseUrl")} value={active.base_url} onChange={(value) => updateProvider(activeProvider, { base_url: value })} />
              <PathField label={t("apiKeyEnv")} value={active.api_key_env} onChange={(value) => updateProvider(activeProvider, { api_key_env: value })} />
              <PathField label={t("tlsCaFile")} value={active.tls_ca_file || ""} onChange={(value) => updateProvider(activeProvider, { tls_ca_file: value })} />
              <NumberField label={t("contextWindow")} value={active.context_window ?? null} onChange={(value) => updateProvider(activeProvider, { context_window: value })} />
              <NumberField label={t("maxOutputTokens")} value={active.max_output_tokens ?? null} onChange={(value) => updateProvider(activeProvider, { max_output_tokens: value })} />
            </div>
            <label className="checkbox-field">
              <input type="checkbox" checked={active.json_mode} onChange={(event) => updateProvider(activeProvider, { json_mode: event.target.checked })} />
              <span>{t("jsonMode")}</span>
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={active.verify_tls ?? true} onChange={(event) => updateProvider(activeProvider, { verify_tls: event.target.checked })} />
              <span>{t("verifyTls")}</span>
            </label>
            <div className="provider-actions">
              <button className="button secondary" onClick={() => onDiscover(active.name)} disabled={!active.name || pendingAction === `${active.name}:discover`} type="button">
                {pendingAction === `${active.name}:discover` ? t("discoveringModel") : t("discoverModels")}
              </button>
              <button className="button secondary" onClick={() => onProbe(active.name, "minimal")} disabled={!active.name || pendingAction === `${active.name}:minimal`} type="button">
                {pendingAction === `${active.name}:minimal` ? t("testingModels") : t("minimalProbe")}
              </button>
              <button className="button secondary" onClick={() => onProbe(active.name, "structured")} disabled={!active.name || pendingAction === `${active.name}:structured`} type="button">
                {pendingAction === `${active.name}:structured` ? t("testingModels") : t("structuredProbe")}
              </button>
              {hasSuggestedConfig(probeResults[active.name]) && (
                <button
                  className="button primary"
                  onClick={() => onApplyCapabilities(active.name, suggestedConfigFor(probeResults[active.name]))}
                  disabled={!active.name || pendingAction === `${active.name}:apply`}
                  type="button"
                >
                  {pendingAction === `${active.name}:apply` ? t("running") : t("applyModelCapabilities")}
                </button>
              )}
              <button className="button secondary" onClick={() => removeProvider(activeProvider)} type="button">
                {t("removeProvider")}
              </button>
            </div>
            <ModelProbeResultPanel
              result={probeResults[active.name]}
              t={t}
              activeModel={active.model}
              onSelectModel={(model) => updateProvider(activeProvider, { model })}
            />
          </div>
        )}
      </div>
    </>
  );
}

function providerRuntimeStatus(provider: ConfigFormProvider, result: ModelProviderProbeState | undefined, t: (key: string) => string): ProviderRuntimeStatus {
  const latest = currentModelProbeResult(provider, result);
  if (latest) {
    if (latest.status === "ok" && latest.available) {
      return {
        tone: "ok",
        dotClass: "online",
        label: t("modelAvailable"),
        detail: latest.message || provider.model || t("noModelSelected"),
        checked: true,
      };
    }
    if (latest.status === "warning" || latest.available) {
      return {
        tone: "warning",
        dotClass: "warning",
        label: t("modelNeedsAttention"),
        detail: latest.message || provider.model || t("noModelSelected"),
        checked: true,
      };
    }
    return {
      tone: "error",
      dotClass: "offline",
      label: t("modelUnavailable"),
      detail: latest.message || provider.model || t("noModelSelected"),
      checked: true,
    };
  }

  if (provider.api_key_env && !provider.api_key_configured) {
    return {
      tone: "error",
      dotClass: "offline",
      label: t("envMissing"),
      detail: provider.api_key_env,
      checked: false,
    };
  }

  const hasMinimumConfig = Boolean(provider.name && provider.model && provider.base_url);
  return {
    tone: hasMinimumConfig ? "unknown" : "warning",
    dotClass: hasMinimumConfig ? "neutral" : "warning",
    label: t("modelNotChecked"),
    detail: hasMinimumConfig ? `${provider.model} · ${t("modelNotCheckedCopy")}` : t("providerMissingRequiredFields"),
    checked: false,
  };
}

function currentModelProbeResult(provider: ConfigFormProvider, result: ModelProviderProbeState | undefined) {
  if (!result) return undefined;
  if (result.probe?.model === provider.model) return result.probe;
  const discoveryModels = result.discovery?.model_ids || [];
  if (result.discovery && (!provider.model || discoveryModels.includes(provider.model))) return result.discovery;
  return undefined;
}

function ModelProbeResultPanel({
  result,
  t,
  activeModel,
  onSelectModel,
}: {
  result?: ModelProviderProbeState;
  t: (key: string) => string;
  activeModel?: string;
  onSelectModel?: (model: string) => void;
}) {
  if (!result?.discovery && !result?.probe) {
    return <p className="settings-action-note">{t("modelProbeEmpty")}</p>;
  }
  const discovery = result.discovery;
  const probe = result.probe;
  const suggested = suggestedConfigFor(result);
  const modelIds = discovery?.model_ids || [];
  return (
    <section className="model-probe-panel">
      <div className="model-probe-header">
        <h3>{t("modelProbeResult")}</h3>
        <span className={`pill ${probe?.status === "ok" || discovery?.status === "ok" ? "success" : probe?.status === "error" || discovery?.status === "error" ? "danger" : ""}`}>
          {probe?.status || discovery?.status || t("unknown")}
        </span>
      </div>
      <p className="panel-copy">{probe?.message || discovery?.message}</p>
      <dl className="model-probe-grid">
        <div>
          <dt>{t("detectedContextWindow")}</dt>
          <dd>{formatMaybeNumber(probe?.detected_context_window ?? discovery?.detected_context_window, t)}</dd>
        </div>
        <div>
          <dt>{t("effectiveContextWindow")}</dt>
          <dd>{formatMaybeNumber(probe?.effective_context_window ?? discovery?.effective_context_window, t)}</dd>
        </div>
        <div>
          <dt>{t("modelCount")}</dt>
          <dd>{formatMaybeNumber(discovery?.model_count, t)}</dd>
        </div>
        <div>
          <dt>{t("latency")}</dt>
          <dd>{probe?.latency_ms ? `${probe.latency_ms} ms` : t("notAvailable")}</dd>
        </div>
        <div>
          <dt>{t("structuredOutput")}</dt>
          <dd>{probe?.structured_output === undefined || probe?.structured_output === null ? t("notAvailable") : probe.structured_output ? t("yes") : t("no")}</dd>
        </div>
        <div>
          <dt>{t("suggestedMaxOutput")}</dt>
          <dd>{formatMaybeNumber(suggested.max_output_tokens, t)}</dd>
        </div>
      </dl>
      {discovery?.configured_model_found === false && activeModel && (
        <p className="settings-action-note warning">{t("configuredModelMissing")}</p>
      )}
      {modelIds.length > 0 && (
        <div className="model-discovery-list">
          <div className="model-discovery-heading">
            <h4>{t("availableModels")}</h4>
            <span>{t("availableModelsCopy")}</span>
          </div>
          <div className="model-discovery-table" role="table" aria-label={t("availableModels")}>
            {modelIds.map((modelId) => {
              const selected = modelId === activeModel;
              return (
                <div className={`model-discovery-row ${selected ? "selected" : ""}`} role="row" key={modelId}>
                  <span className="model-discovery-name" title={modelId}>{modelId}</span>
                  <button className={selected ? "button ghost compact" : "button secondary compact"} type="button" onClick={() => onSelectModel?.(modelId)} disabled={selected}>
                    {selected ? t("selectedModel") : t("useModel")}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

function hasSuggestedConfig(result?: ModelProviderProbeState): boolean {
  const suggested = suggestedConfigFor(result);
  return suggested.context_window !== undefined || suggested.max_output_tokens !== undefined || suggested.json_mode !== undefined;
}

function suggestedConfigFor(result?: ModelProviderProbeState): ModelCapabilitySuggestion {
  const suggested = result?.probe?.suggested_config || result?.discovery?.suggested_config || {};
  const values: ModelCapabilitySuggestion = {};
  if (suggested.context_window !== undefined && suggested.context_window !== null) values.context_window = suggested.context_window;
  if (suggested.max_output_tokens !== undefined && suggested.max_output_tokens !== null) values.max_output_tokens = suggested.max_output_tokens;
  if (suggested.json_mode !== undefined && suggested.json_mode !== null) values.json_mode = suggested.json_mode;
  return values;
}

function formatMaybeNumber(value: number | null | undefined, t: (key: string) => string): string {
  return typeof value === "number" ? value.toLocaleString() : t("notAvailable");
}

function ConnectorCard({ title, checked, onChange, children }: { title: string; checked: boolean; onChange: (checked: boolean) => void; children: ReactNode }) {
  return (
    <section className="settings-subcard">
      <label className="checkbox-field compact">
        <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
        <span>{title}</span>
      </label>
      {children}
    </section>
  );
}

function PathField({
  label,
  value,
  onChange,
  className = "",
  placeholder,
  ariaLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
  ariaLabel?: string;
}) {
  return (
    <label className={`field ${className}`}>
      {label && <span>{label}</span>}
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} aria-label={ariaLabel || label} />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        min={1}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}
      />
    </label>
  );
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}
