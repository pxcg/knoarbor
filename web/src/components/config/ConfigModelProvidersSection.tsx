import { useState, type Dispatch, type SetStateAction } from "react";

import type { ConfigForm, ConfigFormProvider, ConfigImageProvider, ModelCapabilitySuggestion, ModelProviderProbeState } from "../../api/client";
import { NumberField, PathField, PresetMenu } from "./ConfigFormControls";

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

const IMAGE_PROVIDER_PRESETS: ConfigImageProvider[] = [
  {
    name: "sensenova",
    adapter: "sensenova_image",
    base_url: "https://token.sensenova.cn/v1",
    endpoint_path: "/images/generations",
    api_key_env: "SENSENOVA_API_KEY",
    model: "sensenova-u1-fast",
    verify_tls: true,
    tls_ca_file: "",
    response_format: "url",
    size: "",
    aspect_ratio: "16:9",
    image_count: 1,
    extra_body: {},
    api_key_configured: false,
  },
];

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
  const [activeImageProvider, setActiveImageProvider] = useState(0);
  const [imageProviderPreset, setImageProviderPreset] = useState(IMAGE_PROVIDER_PRESETS[0].name);

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

  function updateImageProvider(index: number, patch: Partial<ConfigImageProvider>) {
    setForm({
      ...form,
      image_providers: form.image_providers.map((provider, current) => (current === index ? { ...provider, ...patch } : provider)),
    });
  }

  function addImageProvider() {
    const preset = IMAGE_PROVIDER_PRESETS.find((item) => item.name === imageProviderPreset);
    const template: ConfigImageProvider = preset || {
      name: "",
      adapter: "sensenova_image",
      base_url: "",
      endpoint_path: "/images/generations",
      api_key_env: "",
      model: "",
      verify_tls: true,
      tls_ca_file: "",
      response_format: "url",
      size: "",
      aspect_ratio: "",
      image_count: 1,
      extra_body: {},
      api_key_configured: false,
    };
    const existingNames = new Set(form.image_providers.map((provider) => provider.name));
    let name = template.name;
    if (name && existingNames.has(name)) {
      let suffix = 2;
      while (existingNames.has(`${name}-${suffix}`)) suffix += 1;
      name = `${name}-${suffix}`;
    }
    const nextProviders = [...form.image_providers, { ...template, name }];
    setForm({
      ...form,
      image_providers: nextProviders,
      image_default_provider: form.image_default_provider || name,
    });
    setActiveImageProvider(nextProviders.length - 1);
  }

  function removeImageProvider(index: number) {
    const removedName = form.image_providers[index]?.name;
    const nextProviders = form.image_providers.filter((_, current) => current !== index);
    setForm({
      ...form,
      image_providers: nextProviders,
      image_default_provider: form.image_default_provider === removedName ? nextProviders[0]?.name || "" : form.image_default_provider,
    });
    setActiveImageProvider(Math.min(index, Math.max(0, nextProviders.length - 1)));
  }

  const active = form.providers[activeProvider];
  const activeRuntimeStatus = active ? providerRuntimeStatus(active, probeResults[active.name], t) : null;
  const activeImage = form.image_providers[activeImageProvider];
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
      <div className="settings-inline-action model-provider-toolbar image-provider-toolbar" id="settings-image-models">
        <div>
          <h2>{t("imageModelProviders")}</h2>
          <p className="panel-copy">{t("imageModelProvidersCopy")}</p>
        </div>
        <div className="add-provider-control">
          <PresetMenu
            label={imageProviderPreset || t("custom")}
            options={[...IMAGE_PROVIDER_PRESETS.map((preset) => preset.name), ""]}
            value={imageProviderPreset}
            customLabel={t("custom")}
            ariaLabel={t("imageProviderPreset")}
            onChange={setImageProviderPreset}
          />
          <button className="button secondary" onClick={addImageProvider} type="button">
            {t("addImageProvider")}
          </button>
        </div>
      </div>
      <div className="provider-workspace image-provider-workspace">
        <div className="provider-list">
          {form.image_providers.map((provider, index) => {
            const ready = Boolean(provider.name && provider.model && provider.base_url);
            const missingKey = Boolean(provider.api_key_env && !provider.api_key_configured);
            return (
              <button className={`provider-row ${index === activeImageProvider ? "active" : ""} ${missingKey ? "error" : ready ? "unknown" : "warning"}`} key={`${provider.name}:${index}`} onClick={() => setActiveImageProvider(index)} type="button">
                <span className={`status-dot ${missingKey ? "offline" : ready ? "neutral" : "warning"}`} />
                <strong>{provider.name || t("untitledProvider")}</strong>
                <small title={provider.model || provider.api_key_env || t("providerMissingRequiredFields")}>{missingKey ? `${t("envMissing")} · ${provider.api_key_env}` : provider.model || t("providerMissingRequiredFields")}</small>
              </button>
            );
          })}
          {!form.image_providers.length && <div className="empty-state">{t("noImageProviders")}</div>}
        </div>
        {activeImage && (
          <div className={`provider-card ${activeImage.api_key_env && !activeImage.api_key_configured ? "error" : "unknown"}`}>
            <div className="provider-card-header">
              <div>
                <h3>{activeImage.name || t("newImageProvider")}</h3>
                <p className="panel-copy">{t("imageProviderCopy")}</p>
              </div>
              <div className={`provider-status ${activeImage.api_key_env && !activeImage.api_key_configured ? "error" : "unknown"}`}>
                <span className={`status-dot ${activeImage.api_key_env && !activeImage.api_key_configured ? "offline" : "neutral"}`} />
                <span>{activeImage.api_key_env && !activeImage.api_key_configured ? t("envMissing") : t("modelNotChecked")}</span>
              </div>
            </div>
            <div className="form-grid provider-form-grid">
              <PathField label={t("name")} value={activeImage.name} onChange={(value) => updateImageProvider(activeImageProvider, { name: value })} />
              <label className="field">
                <span>{t("modelAdapter")}</span>
                <select value={activeImage.adapter || "sensenova_image"} onChange={(event) => updateImageProvider(activeImageProvider, { adapter: event.target.value as ConfigImageProvider["adapter"] })}>
                  <option value="sensenova_image">{t("adapterSenseNovaImage")}</option>
                </select>
              </label>
              <PathField label={t("model")} value={activeImage.model} onChange={(value) => updateImageProvider(activeImageProvider, { model: value })} />
              <PathField label={t("baseUrl")} value={activeImage.base_url} onChange={(value) => updateImageProvider(activeImageProvider, { base_url: value })} />
              <PathField label={t("imageEndpointPath")} value={activeImage.endpoint_path} onChange={(value) => updateImageProvider(activeImageProvider, { endpoint_path: value })} />
              <PathField label={t("apiKeyEnv")} value={activeImage.api_key_env} onChange={(value) => updateImageProvider(activeImageProvider, { api_key_env: value })} />
              <SecretField
                configured={activeImage.api_key_configured}
                configuredLabel={t("configured")}
                label={t("apiKey")}
                placeholder={t(activeImage.api_key_configured ? "apiKeyConfiguredPlaceholder" : "apiKeyPlaceholder")}
                value={activeImage.api_key_value || ""}
                onChange={(value) => updateImageProvider(activeImageProvider, { api_key_value: value })}
              />
              <PathField label={t("tlsCaFile")} value={activeImage.tls_ca_file || ""} onChange={(value) => updateImageProvider(activeImageProvider, { tls_ca_file: value })} />
              <label className="field">
                <span>{t("imageResponseFormat")}</span>
                <select value={activeImage.response_format || "url"} onChange={(event) => updateImageProvider(activeImageProvider, { response_format: event.target.value })}>
                  <option value="url">url</option>
                  <option value="b64_json">b64_json</option>
                </select>
              </label>
              <PathField label={t("imageSize")} value={activeImage.size || ""} onChange={(value) => updateImageProvider(activeImageProvider, { size: value })} />
              <PathField label={t("imageAspectRatio")} value={activeImage.aspect_ratio || ""} onChange={(value) => updateImageProvider(activeImageProvider, { aspect_ratio: value })} />
              <NumberField label={t("imageCount")} value={activeImage.image_count ?? 1} onChange={(value) => updateImageProvider(activeImageProvider, { image_count: value || 1 })} />
            </div>
            <label className="checkbox-field">
              <input type="checkbox" checked={activeImage.verify_tls ?? true} onChange={(event) => updateImageProvider(activeImageProvider, { verify_tls: event.target.checked })} />
              <span>{t("verifyTls")}</span>
            </label>
            <div className="provider-actions">
              <button className="button secondary" onClick={() => removeImageProvider(activeImageProvider)} type="button">
                {t("removeImageProvider")}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function SecretField({
  configured,
  configuredLabel,
  label,
  onChange,
  placeholder,
  value,
}: {
  configured: boolean;
  configuredLabel: string;
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <label className="field">
      <span>
        {label}
        {configured && <small className="field-inline-status">{configuredLabel}</small>}
      </span>
      <input
        autoComplete="off"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type="password"
        value={value}
      />
    </label>
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
      <p className="settings-action-note">{t("modelProbeResultCopy")}</p>
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
