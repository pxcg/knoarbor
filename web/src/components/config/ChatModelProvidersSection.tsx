import { useState, type Dispatch, type SetStateAction } from "react";

import type { AppNotice } from "../../appContext";
import type { ConfigForm, ConfigFormProvider, ModelProviderProbeState } from "../../api/client";
import { PathField, PresetMenu } from "./ConfigFormControls";
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
  onCommit: (nextForm: ConfigForm) => Promise<void>;
  onError: (notice: AppNotice | null) => void;
};

export function ChatModelProvidersSection({ form, setForm, t, probeResults, pendingAction, onDiscover, onCommit, onError }: ChatModelProvidersSectionProps) {
  const [activeProvider, setActiveProvider] = useState(0);
  const [providerPreset, setProviderPreset] = useState(PROVIDER_PRESETS[0].name);

  function uniqueProviderName(baseName: string): string {
    const existingNames = new Set(form.providers.map((provider) => provider.name.trim()).filter(Boolean));
    if (!existingNames.has(baseName)) return baseName;
    let suffix = 2;
    while (existingNames.has(`${baseName}-${suffix}`)) suffix += 1;
    return `${baseName}-${suffix}`;
  }

  function savedProviderIndex(providers: ConfigFormProvider[], name: string): number {
    return [...providers].sort((left, right) => (left.name < right.name ? -1 : left.name > right.name ? 1 : 0)).findIndex((provider) => provider.name === name);
  }

  async function commit(nextForm: ConfigForm): Promise<boolean> {
    const previousForm = form;
    setForm(nextForm);
    try {
      await onCommit(nextForm);
      return true;
    } catch (error) {
      setForm(previousForm);
      onError({ message: error instanceof Error ? error.message : String(error), error: true });
      return false;
    }
  }

  function updateProvider(index: number, patch: Partial<ConfigFormProvider>) {
    setForm({
      ...form,
      providers: form.providers.map((provider, current) => (current === index ? { ...provider, ...patch } : provider)),
    });
  }

  function providerPatchForm(index: number, patch: Partial<ConfigFormProvider>): ConfigForm {
    const previousProvider = form.providers[index];
    const nextProviders = form.providers.map((provider, current) => (current === index ? { ...provider, ...patch } : provider));
    const nextDefaultProvider = patch.name && form.default_provider === previousProvider?.name ? patch.name : form.default_provider;
    return {
      ...form,
      providers: nextProviders,
      default_provider: nextDefaultProvider || nextProviders[index]?.name || "",
    };
  }

  function selectDiscoveredModel(index: number, model: string) {
    void commit(providerPatchForm(index, { model }));
  }

  async function addProvider() {
    const preset = PROVIDER_PRESETS.find((item) => item.name === providerPreset);
    const template = preset || {
      name: "custom",
      base_url: "",
      adapter: "openai_compatible",
      api_key: "",
      model: "",
      json_mode: true,
      tls_ca_file: "",
      context_window: null,
      max_output_tokens: null,
      extra_body: {},
    };
    const name = uniqueProviderName(template.name);
    const nextProviders = [...form.providers, { ...template, name }];
    if (await commit({ ...form, providers: nextProviders, default_provider: form.default_provider || name })) {
      setActiveProvider(savedProviderIndex(nextProviders, name));
    }
  }

  async function removeProvider(index: number) {
    const removedName = form.providers[index]?.name;
    const nextProviders = form.providers.filter((_, current) => current !== index);
    if (await commit({
      ...form,
      providers: nextProviders,
      default_provider: form.default_provider === removedName ? nextProviders[0]?.name || "" : form.default_provider,
    })) {
      setActiveProvider(Math.min(index, Math.max(0, nextProviders.length - 1)));
    }
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
          <button className="button secondary" onClick={() => void addProvider()} type="button">
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
              <PathField label={t("name")} value={active.name} onBlur={(value) => void commit(providerPatchForm(activeProvider, { name: value }))} onChange={(value) => updateProvider(activeProvider, { name: value })} />
              <PathField label={t("model")} value={active.model} onBlur={(value) => void commit(providerPatchForm(activeProvider, { model: value }))} onChange={(value) => updateProvider(activeProvider, { model: value })} />
              <PathField label={t("baseUrl")} value={active.base_url} onBlur={(value) => void commit(providerPatchForm(activeProvider, { base_url: value }))} onChange={(value) => updateProvider(activeProvider, { base_url: value })} />
              <SecretField
                label={t("apiKey")}
                placeholder={t("apiKeyPlaceholder")}
                value={active.api_key || ""}
                onBlur={(value) => void commit(providerPatchForm(activeProvider, { api_key: value }))}
                onChange={(value) => updateProvider(activeProvider, { api_key: value })}
              />
              <PathField
                label={t("tlsCaFile")}
                value={active.tls_ca_file || ""}
                onBlur={(value) => void commit(providerPatchForm(activeProvider, { tls_ca_file: value }))}
                onChange={(value) => updateProvider(activeProvider, { tls_ca_file: value })}
                selectFileTitle={t("tlsCaFile")}
                t={t}
              />
            </div>
            <div className="provider-actions">
              <button className="button secondary" onClick={() => onDiscover(active.name)} disabled={!active.name || pendingAction === `${active.name}:discover`} type="button">
                {pendingAction === `${active.name}:discover` ? t("discoveringModel") : t("discoverModels")}
              </button>
              <button className="button secondary" onClick={() => void removeProvider(activeProvider)} type="button">
                {t("removeProvider")}
              </button>
            </div>
            <ModelProbeResultPanel result={probeResults[active.name]} t={t} activeModel={active.model} onSelectModel={(model) => selectDiscoveredModel(activeProvider, model)} />
          </div>
        )}
      </div>
    </>
  );
}
