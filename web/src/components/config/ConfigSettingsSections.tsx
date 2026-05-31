import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useState } from "react";

import type { ConfigForm, ConfigFormProvider } from "../../api/client";
import { BrandIcon, type BrandIconName } from "../BrandIcon";

type SectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
};

const PROVIDER_PRESETS: ConfigFormProvider[] = [
  {
    name: "deepseek",
    base_url: "https://api.deepseek.com",
    api_key_env: "DEEPSEEK_API_KEY",
    model: "deepseek-v4-flash",
    json_mode: true,
    api_key_configured: false,
  },
  {
    name: "openai",
    base_url: "https://api.openai.com/v1",
    api_key_env: "OPENAI_API_KEY",
    model: "gpt-4.1",
    json_mode: true,
    api_key_configured: false,
  },
  {
    name: "vllm",
    base_url: "http://localhost:8000/v1",
    api_key_env: "VLLM_API_KEY",
    model: "local-model",
    json_mode: true,
    api_key_configured: false,
  },
  {
    name: "ollama",
    base_url: "http://localhost:11434/v1",
    api_key_env: "OLLAMA_API_KEY",
    model: "qwen2.5:14b",
    json_mode: true,
    api_key_configured: false,
  },
];

export function ConfigBasicSection({ form, setForm, t }: SectionProps) {
  return (
    <div className="form-grid config-basic-grid" id="settings-basic">
      <label className="field">
        <span>{t("projectName")}</span>
        <input value={form.project_name} onChange={(event) => setForm({ ...form, project_name: event.target.value })} placeholder={t("projectNamePlaceholder")} />
      </label>
      <label className="field">
        <span>{t("vaultPath")}</span>
        <input value={form.vault_path} onChange={(event) => setForm({ ...form, vault_path: event.target.value })} placeholder="./wiki" />
      </label>
    </div>
  );
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
          <PathField label={t("nonMarkdownInputDir")} value={form.mineru_input_dir} onChange={(value) => setForm({ ...form, mineru_input_dir: value })} placeholder="./wiki/raw/documents/originals" />
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

export function ConfigModelProvidersSection({ form, setForm, t }: SectionProps) {
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
      api_key_env: "",
      model: "",
      json_mode: true,
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
  return (
    <>
      <div className="section-divider" id="settings-models">
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
          <button className="button secondary" onClick={addProvider}>
            {t("addProvider")}
          </button>
        </div>
      </div>
      <div className="provider-workspace">
        <div className="provider-list">
          {form.providers.map((provider, index) => (
            <button className={`provider-row ${index === activeProvider ? "active" : ""}`} key={`${provider.name}:${index}`} onClick={() => setActiveProvider(index)} type="button">
              <span className={`status-dot ${provider.api_key_configured ? "online" : "offline"}`} />
              <strong>{provider.name || t("untitledProvider")}</strong>
              <small>{provider.model || t("noModelSelected")}</small>
            </button>
          ))}
          {!form.providers.length && <div className="empty-state">{t("noProviders")}</div>}
        </div>

        {active && (
          <div className="provider-card">
            <div className="provider-card-header">
              <div>
                <h3>{active.name || t("newProvider")}</h3>
                <p className="panel-copy">{t("providerCopy")}</p>
              </div>
              <div className="provider-status">
                <span className={`status-dot ${active.api_key_configured ? "online" : "offline"}`} />
                {active.api_key_env ? (active.api_key_configured ? t("envConfigured") : t("envMissing")) : t("noEnv")}
              </div>
            </div>
            <div className="form-grid provider-form-grid">
              <PathField label={t("name")} value={active.name} onChange={(value) => updateProvider(activeProvider, { name: value })} />
              <PathField label={t("model")} value={active.model} onChange={(value) => updateProvider(activeProvider, { model: value })} />
              <PathField label={t("baseUrl")} value={active.base_url} onChange={(value) => updateProvider(activeProvider, { base_url: value })} />
              <PathField label={t("apiKeyEnv")} value={active.api_key_env} onChange={(value) => updateProvider(activeProvider, { api_key_env: value })} />
            </div>
            <label className="checkbox-field">
              <input type="checkbox" checked={active.json_mode} onChange={(event) => updateProvider(activeProvider, { json_mode: event.target.checked })} />
              <span>{t("jsonMode")}</span>
            </label>
            <div className="provider-actions">
              <button className="button secondary" onClick={() => removeProvider(activeProvider)}>
                {t("removeProvider")}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
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

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}
