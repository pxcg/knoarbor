import { useState, type Dispatch, type SetStateAction } from "react";

import type { ConfigForm, ConfigImageProvider, ImageProviderProbeResponse } from "../../api/client";
import { NumberField, PathField, PresetMenu } from "./ConfigFormControls";
import { IMAGE_PROVIDER_PRESETS } from "./ConfigModelProviderPresets";
import { SecretField } from "./ConfigSecretField";

type ImageModelProvidersSectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
  probeResults: Record<string, ImageProviderProbeResponse>;
  pendingProvider: string | null;
  onProbe: (provider: string) => void;
  onProbeInvalidated: (provider: string) => void;
  onCommit: (nextForm: ConfigForm) => Promise<void>;
  onError: (error: unknown) => void;
};

const IMAGE_ADAPTERS: Array<ConfigImageProvider["adapter"]> = ["sensenova_image", "openai_chat_image"];

export function ImageModelProvidersSection({
  form,
  setForm,
  t,
  probeResults,
  pendingProvider,
  onProbe,
  onProbeInvalidated,
  onCommit,
  onError,
}: ImageModelProvidersSectionProps) {
  const [activeImageProvider, setActiveImageProvider] = useState(0);
  const [imageProviderPreset, setImageProviderPreset] = useState("");

  async function commit(nextForm: ConfigForm): Promise<boolean> {
    const previousForm = form;
    setForm(nextForm);
    try {
      await onCommit(nextForm);
      return true;
    } catch (error) {
      setForm((current) => current === nextForm ? previousForm : current);
      onError(error);
      return false;
    }
  }

  function updateImageProvider(index: number, patch: Partial<ConfigImageProvider>) {
    const previousName = form.image_providers[index]?.name;
    if (previousName) onProbeInvalidated(previousName);
    setForm({
      ...form,
      image_providers: form.image_providers.map((provider, current) => (current === index ? { ...provider, ...patch } : provider)),
    });
  }

  function imageProviderPatchForm(index: number, patch: Partial<ConfigImageProvider>): ConfigForm {
    const previousProvider = form.image_providers[index];
    const nextProviders = form.image_providers.map((provider, current) => (current === index ? { ...provider, ...patch } : provider));
    const nextDefaultProvider = patch.name && form.image_default_provider === previousProvider?.name ? patch.name : form.image_default_provider;
    return {
      ...form,
      image_providers: nextProviders,
      image_default_provider: nextDefaultProvider || nextProviders[index]?.name || "",
    };
  }

  async function addImageProvider() {
    const preset = IMAGE_PROVIDER_PRESETS.find((item) => item.name === imageProviderPreset);
    const template: ConfigImageProvider = preset || {
      name: "",
      adapter: "sensenova_image",
      base_url: "",
      endpoint_path: "/images/generations",
      api_key: "",
      model: "",
      tls_ca_file: "",
      resolution: "2720*1536",
      num_inference_steps: 20,
      guidance: 4,
      extra_body: {},
    };
    const existingNames = new Set(form.image_providers.map((provider) => provider.name));
    let name = template.name;
    if (name && existingNames.has(name)) {
      let suffix = 2;
      while (existingNames.has(`${name}-${suffix}`)) suffix += 1;
      name = `${name}-${suffix}`;
    }
    const nextProviders = [...form.image_providers, { ...template, name }];
    if (await commit({
      ...form,
      image_providers: nextProviders,
      image_default_provider: form.image_default_provider || name,
    })) {
      setActiveImageProvider(nextProviders.length - 1);
    }
  }

  async function removeImageProvider(index: number) {
    const removedName = form.image_providers[index]?.name;
    const nextProviders = form.image_providers.filter((_, current) => current !== index);
    if (await commit({
      ...form,
      image_providers: nextProviders,
      image_default_provider: form.image_default_provider === removedName ? nextProviders[0]?.name || "" : form.image_default_provider,
    })) {
      setActiveImageProvider(Math.min(index, Math.max(0, nextProviders.length - 1)));
    }
  }

  const activeImage = form.image_providers[activeImageProvider];
  const activeProbe = activeImage?.name ? probeResults[activeImage.name] : undefined;
  const probePending = Boolean(activeImage?.name && pendingProvider === activeImage.name);

  return (
    <>
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
          <button className="button secondary" onClick={() => void addImageProvider()} type="button">
            {t("addImageProvider")}
          </button>
        </div>
      </div>
      <div className="provider-workspace image-provider-workspace">
        <div className="provider-list">
          {form.image_providers.map((provider, index) => {
            const ready = Boolean(provider.name && provider.model && provider.base_url);
            const probe = provider.name ? probeResults[provider.name] : undefined;
            const tone = probe?.status || (ready ? "unknown" : "warning");
            const dotClass = probe?.available ? "online" : probe?.status === "error" ? "offline" : ready ? "neutral" : "warning";
            return (
              <button className={`provider-row ${index === activeImageProvider ? "active" : ""} ${tone}`} key={`${provider.name}:${index}`} onClick={() => setActiveImageProvider(index)} type="button">
                <span className={`status-dot ${dotClass}`} />
                <strong>{provider.name || t("untitledProvider")}</strong>
                <small title={provider.model || t("providerMissingRequiredFields")}>{provider.model || t("providerMissingRequiredFields")}</small>
              </button>
            );
          })}
          {!form.image_providers.length && <div className="empty-state">{t("noImageProviders")}</div>}
        </div>
        {activeImage && (
          <div className={`provider-card ${activeProbe?.status || "unknown"}`}>
            <div className="provider-card-header">
              <div>
                <h3>{activeImage.name || t("newImageProvider")}</h3>
                <p className="panel-copy">{t("imageProviderCopy")}</p>
              </div>
              <div className={`provider-status ${activeProbe?.status || "unknown"}`}>
                <span className={`status-dot ${activeProbe?.status === "ok" ? "online" : activeProbe?.status === "error" ? "offline" : "neutral"}`} />
                <span>{activeProbe ? (activeProbe.available ? t("imageProbeAvailable") : t("imageProbeUnavailable")) : t("modelNotChecked")}</span>
              </div>
            </div>
            <div className="form-grid provider-form-grid">
              <PathField label={t("name")} value={activeImage.name} onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { name: value }))} onChange={(value) => updateImageProvider(activeImageProvider, { name: value })} />
              <div className="field compact-field">
                <span>{t("imageAdapter")}</span>
                <div className="settings-language-options" role="group" aria-label={t("imageAdapter")}>
                  {IMAGE_ADAPTERS.map((adapter) => (
                    <button
                      className={`button ${activeImage.adapter === adapter ? "primary" : "secondary"}`}
                      key={adapter}
                      onClick={() => void commit(imageProviderPatchForm(activeImageProvider, adapterDefaults(adapter)))}
                      type="button"
                    >
                      {t(`imageAdapter.${adapter}`)}
                    </button>
                  ))}
                </div>
              </div>
              <PathField label={t("model")} value={activeImage.model} onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { model: value }))} onChange={(value) => updateImageProvider(activeImageProvider, { model: value })} />
              <PathField label={t("baseUrl")} placeholder={t("baseUrlPlaceholder")} value={activeImage.base_url} onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { base_url: value }))} onChange={(value) => updateImageProvider(activeImageProvider, { base_url: value })} />
              <PathField label={t("imageEndpointPath")} value={activeImage.endpoint_path} onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { endpoint_path: value }))} onChange={(value) => updateImageProvider(activeImageProvider, { endpoint_path: value })} />
              <SecretField
                label={t("apiKey")}
                placeholder={t("apiKeyPlaceholder")}
                value={activeImage.api_key || ""}
                onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { api_key: value }))}
                onChange={(value) => updateImageProvider(activeImageProvider, { api_key: value })}
              />
              <PathField
                label={t("tlsCaFile")}
                value={activeImage.tls_ca_file || ""}
                onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { tls_ca_file: value }))}
                onChange={(value) => updateImageProvider(activeImageProvider, { tls_ca_file: value })}
                selectFileTitle={t("tlsCaFile")}
                t={t}
              />
              <PathField label={t("imageResolution")} value={activeImage.resolution || "2720*1536"} onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { resolution: value }))} onChange={(value) => updateImageProvider(activeImageProvider, { resolution: value })} />
              <NumberField
                label={t("imageSteps")}
                value={activeImage.num_inference_steps ?? 20}
                onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { num_inference_steps: value || 20 }))}
                onChange={(value) => updateImageProvider(activeImageProvider, { num_inference_steps: value || 20 })}
              />
              <NumberField
                label={t("imageGuidance")}
                value={activeImage.guidance ?? 4}
                min={0}
                step="any"
                onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { guidance: value ?? 4 }))}
                onChange={(value) => updateImageProvider(activeImageProvider, { guidance: value ?? 4 })}
              />
            </div>
            {activeProbe && (
              <div className={`model-probe-panel ${activeProbe.status}`}>
                <div className="model-probe-header">
                  <h3>{t("imageProbeResult")}</h3>
                  <span>{activeProbe.elapsed_ms} ms</span>
                </div>
                <p className={`provider-status-message ${activeProbe.status}`}>{activeProbe.message}</p>
                {activeProbe.available && <p className="panel-copy">{t("imageProbeImages")}: {activeProbe.image_count}</p>}
              </div>
            )}
            <div className="provider-actions">
              <button
                className="button primary"
                disabled={probePending || !activeImage.name || !activeImage.model || !activeImage.base_url}
                onClick={() => onProbe(activeImage.name)}
                type="button"
              >
                {probePending ? t("probingImageModel") : t("probeImageModel")}
              </button>
              <button className="button secondary" onClick={() => void removeImageProvider(activeImageProvider)} type="button">
                {t("removeImageProvider")}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function adapterDefaults(adapter: ConfigImageProvider["adapter"]): Partial<ConfigImageProvider> {
  if (adapter === "openai_chat_image") {
    return { adapter, endpoint_path: "/chat/completions", resolution: "" };
  }
  return { adapter, endpoint_path: "/images/generations", resolution: "2720*1536" };
}
