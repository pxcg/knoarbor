import { useState, type Dispatch, type SetStateAction } from "react";

import type { ConfigForm, ConfigImageProvider } from "../../api/client";
import { NumberField, PathField, PresetMenu } from "./ConfigFormControls";
import { IMAGE_PROVIDER_PRESETS } from "./ConfigModelProviderPresets";
import { SecretField } from "./ConfigSecretField";

type ImageModelProvidersSectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
};

export function ImageModelProvidersSection({ form, setForm, t }: ImageModelProvidersSectionProps) {
  const [activeImageProvider, setActiveImageProvider] = useState(0);
  const [imageProviderPreset, setImageProviderPreset] = useState(IMAGE_PROVIDER_PRESETS[0].name);

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
      resolution: "2720*1536",
      num_inference_steps: 20,
      guidance: 4,
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

  const activeImage = form.image_providers[activeImageProvider];

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
              <PathField
                label={t("tlsCaFile")}
                value={activeImage.tls_ca_file || ""}
                onChange={(value) => updateImageProvider(activeImageProvider, { tls_ca_file: value })}
                selectFileTitle={t("tlsCaFile")}
                t={t}
              />
              <PathField label={t("imageResolution")} value={activeImage.resolution || "2720*1536"} onChange={(value) => updateImageProvider(activeImageProvider, { resolution: value })} />
              <NumberField label={t("imageSteps")} value={activeImage.num_inference_steps ?? 20} onChange={(value) => updateImageProvider(activeImageProvider, { num_inference_steps: value || 20 })} />
              <NumberField label={t("imageGuidance")} value={activeImage.guidance ?? 4} min={0} step="any" onChange={(value) => updateImageProvider(activeImageProvider, { guidance: value ?? 4 })} />
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
