import { useState, type Dispatch, type SetStateAction } from "react";

import type { ConfigForm, ConfigFormProvider, ModelProviderProbeState } from "../../api/client";
import { NumberField, PathField, PresetMenu } from "./ConfigFormControls";
import { ModelProbeResultPanel } from "./ConfigModelProbeResultPanel";
import { PROVIDER_PRESETS } from "./ConfigModelProviderPresets";
import { providerRuntimeStatus } from "./ConfigModelProviderStatus";
import { SecretField } from "./ConfigSecretField";

type ChatModelProvidersSectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
  probeResults: Record<string, ModelProviderProbeState>;
  pendingAction: string | null;
  onDiscover: (provider: string) => void;
  onProbe: (provider: string) => void;
};

export function ChatModelProvidersSection({ form, setForm, t, probeResults, pendingAction, onDiscover, onProbe }: ChatModelProvidersSectionProps) {
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
          <h2>{t("chatModelProviders")}</h2>
          <p className="panel-copy">{t("chatModelProvidersCopy")}</p>
        </div>
        <div className="add-provider-control">
          <PresetMenu
            label={providerPreset || t("custom")}
            options={[...PROVIDER_PRESETS.map((preset) => preset.name), ""]}
            value={providerPreset}
            customLabel={t("custom")}
            ariaLabel={t("providerPreset")}
            onChange={setProviderPreset}
          />
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
              <SecretField
                configured={active.api_key_configured}
                configuredLabel={t("configured")}
                label={t("apiKey")}
                placeholder={t(active.api_key_configured ? "apiKeyConfiguredPlaceholder" : "apiKeyPlaceholder")}
                value={active.api_key_value || ""}
                onChange={(value) => updateProvider(activeProvider, { api_key_value: value })}
              />
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
              <button className="button secondary" onClick={() => onProbe(active.name)} disabled={!active.name || pendingAction === `${active.name}:connectivity`} type="button">
                {pendingAction === `${active.name}:connectivity` ? t("testingModels") : t("minimalProbe")}
              </button>
              <button className="button secondary" onClick={() => removeProvider(activeProvider)} type="button">
                {t("removeProvider")}
              </button>
            </div>
            <ModelProbeResultPanel result={probeResults[active.name]} t={t} activeModel={active.model} onSelectModel={(model) => updateProvider(activeProvider, { model })} />
          </div>
        )}
      </div>
    </>
  );
}
