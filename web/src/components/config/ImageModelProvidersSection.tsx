import { useState, type Dispatch, type SetStateAction } from "react";

import type { AppNotice } from "../../appContext";
import type { ConfigForm, ConfigImageProvider } from "../../api/client";
import { NumberField, PathField, PresetMenu } from "./ConfigFormControls";
import { IMAGE_PROVIDER_PRESETS } from "./ConfigModelProviderPresets";
import { SecretField } from "./ConfigSecretField";

type ImageModelProvidersSectionProps = {
  form: ConfigForm;
  setForm: Dispatch<SetStateAction<ConfigForm | null>>;
  t: (key: string) => string;
  onCommit: (nextForm: ConfigForm) => Promise<void>;
  onError: (notice: AppNotice | null) => void;
};

export function ImageModelProvidersSection({ form, setForm, t, onCommit, onError }: ImageModelProvidersSectionProps) {
  const [activeImageProvider, setActiveImageProvider] = useState(0);
  const [imageProviderPreset, setImageProviderPreset] = useState(IMAGE_PROVIDER_PRESETS[0].name);

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

  function updateImageProvider(index: number, patch: Partial<ConfigImageProvider>) {
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
            return (
              <button className={`provider-row ${index === activeImageProvider ? "active" : ""} ${ready ? "unknown" : "warning"}`} key={`${provider.name}:${index}`} onClick={() => setActiveImageProvider(index)} type="button">
                <span className={`status-dot ${ready ? "neutral" : "warning"}`} />
                <strong>{provider.name || t("untitledProvider")}</strong>
                <small title={provider.model || t("providerMissingRequiredFields")}>{provider.model || t("providerMissingRequiredFields")}</small>
              </button>
            );
          })}
          {!form.image_providers.length && <div className="empty-state">{t("noImageProviders")}</div>}
        </div>
        {activeImage && (
          <div className="provider-card unknown">
            <div className="provider-card-header">
              <div>
                <h3>{activeImage.name || t("newImageProvider")}</h3>
                <p className="panel-copy">{t("imageProviderCopy")}</p>
              </div>
              <div className="provider-status unknown">
                <span className="status-dot neutral" />
                <span>{t("modelNotChecked")}</span>
              </div>
            </div>
            <div className="form-grid provider-form-grid">
              <PathField label={t("name")} value={activeImage.name} onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { name: value }))} onChange={(value) => updateImageProvider(activeImageProvider, { name: value })} />
              <PathField label={t("model")} value={activeImage.model} onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { model: value }))} onChange={(value) => updateImageProvider(activeImageProvider, { model: value })} />
              <PathField label={t("baseUrl")} value={activeImage.base_url} onBlur={(value) => void commit(imageProviderPatchForm(activeImageProvider, { base_url: value }))} onChange={(value) => updateImageProvider(activeImageProvider, { base_url: value })} />
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
            <div className="provider-actions">
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
