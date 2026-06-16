import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  applyModelCapabilities,
  discoverModelProvider,
  getConfigDiagnostics,
  getConfigForm,
  probeModelProvider,
  saveConfig,
	  saveConfigForm,
	  type ConfigForm,
	  type ModelCapabilitySuggestion,
	} from "../api/client";
import type { AppContext } from "../App";
import { ConfigDiagnosticsPanel } from "../components/config/ConfigDiagnosticsPanel";
import {
  ConfigBasicSection,
  ConfigInputsSection,
  ConfigModelProvidersSection,
  ConfigPreprocessingSection,
  ConfigRuntimeSection,
} from "../components/config/ConfigSettingsSections";

type Props = {
  context: AppContext;
  embedded?: boolean;
};

export function ConfigPage({ context, embedded = false }: Props) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ConfigForm | null>(null);
  const [activeSection, setActiveSection] = useState<ConfigSectionId>("basic");

  const formQuery = useQuery({
    queryKey: ["config-form", context.configPath],
    queryFn: () => getConfigForm(context.configPath),
    staleTime: 5 * 60_000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  const diagnosticsQuery = useQuery({
    queryKey: ["config-diagnostics", context.configPath],
    queryFn: () => getConfigDiagnostics(context.configPath),
    enabled: Boolean(formQuery.data),
    staleTime: 5 * 60_000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (formQuery.data) setForm(normalizeConfigForm(formQuery.data));
  }, [formQuery.data]);

  useEffect(() => {
    const error = formQuery.error || diagnosticsQuery.error;
    if (error) context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
  }, [context, diagnosticsQuery.error, formQuery.error]);

  async function updateSettingsFromDisk() {
    await queryClient.invalidateQueries({ queryKey: ["config-form"] });
    await queryClient.invalidateQueries({ queryKey: ["config-diagnostics"] });
    await queryClient.invalidateQueries({ queryKey: ["models", "providers"] });
    await formQuery.refetch();
    await diagnosticsQuery.refetch();
    await context.refreshAll();
  }

  const structuredSave = useMutation({
    mutationFn: async () => {
      if (!form) throw new Error("Configuration form is not loaded.");
      return saveConfigForm(context.configPath, form);
    },
    onSuccess: async (response) => {
      context.setConfigPath(response.config_path);
      context.setConfigExists(true);
      context.setSummary(response.summary || {});
      await updateSettingsFromDisk();
      context.setNotice({ message: `${context.t("configurationSaved")} ${response.config_path}` });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  const yamlSave = useMutation({
    mutationFn: () => saveConfig(context.configPath, context.configContent),
    onSuccess: async (response) => {
      context.setConfigPath(response.config_path);
      context.setConfigExists(true);
      context.setSummary(response.summary || {});
      await updateSettingsFromDisk();
      context.setNotice({ message: `${context.t("yamlConfigurationSaved")} ${response.config_path}` });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  const saving = structuredSave.isPending || yamlSave.isPending;

  async function saveCurrentFormForModelAction(): Promise<string | null> {
    if (!form) throw new Error("Configuration form is not loaded.");
    const response = await saveConfigForm(context.configPath, form);
    context.setConfigPath(response.config_path);
    context.setConfigExists(true);
    context.setSummary(response.summary || {});
    await queryClient.invalidateQueries({ queryKey: ["config-form"] });
    await queryClient.invalidateQueries({ queryKey: ["config-diagnostics"] });
    await queryClient.invalidateQueries({ queryKey: ["models", "providers"] });
    return response.config_path;
  }

  const discoverMutation = useMutation({
    mutationFn: async (provider: string) => {
      const configPath = await saveCurrentFormForModelAction();
      return discoverModelProvider(configPath, provider);
    },
    onSuccess: (result) => {
      context.setModelProbeResults((current) => ({
        ...current,
        [result.provider]: { ...(current[result.provider] || {}), discovery: result, lastAction: "discover" },
      }));
      void diagnosticsQuery.refetch();
      context.setNotice({ message: result.message, error: !result.available });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  const probeMutation = useMutation({
    mutationFn: async ({ provider, level }: { provider: string; level: "minimal" | "structured" }) => {
      const configPath = await saveCurrentFormForModelAction();
      return probeModelProvider(configPath, provider, level);
    },
    onSuccess: (result) => {
      context.setModelProbeResults((current) => ({
        ...current,
        [result.provider]: { ...(current[result.provider] || {}), probe: result, lastAction: result.level },
      }));
      void diagnosticsQuery.refetch();
      context.setNotice({ message: result.message, error: result.status === "error" });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  const applyCapabilitiesMutation = useMutation({
    mutationFn: async ({ provider, values }: { provider: string; values: ModelCapabilitySuggestion }) => {
      const configPath = await saveCurrentFormForModelAction();
      return applyModelCapabilities(configPath, provider, values);
    },
    onSuccess: async (result) => {
      await updateSettingsFromDisk();
      context.setNotice({ message: `${context.t("modelCapabilitiesApplied")} ${Object.keys(result.applied).join(", ")}` });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  return (
    <section className={embedded ? "settings-embedded" : "view active"}>
      <article className={embedded ? "settings-embedded-panel" : "panel"}>
        <div className="panel-header">
          <div>
            <h2>{context.t("configuration")}</h2>
            <p className="panel-copy">{context.t("configurationCopy")}</p>
          </div>
          <div className="button-row">
            <button
              className="button secondary"
              onClick={async () => {
                await updateSettingsFromDisk();
                context.setNotice({ message: context.t("refreshComplete") });
              }}
              disabled={formQuery.isFetching || diagnosticsQuery.isFetching}
            >
              {context.t("refresh")}
            </button>
            <button className="button primary" onClick={() => structuredSave.mutate()} disabled={!form || saving}>
              {saving ? context.t("running") : context.t("saveSettings")}
            </button>
          </div>
        </div>

        {formQuery.isLoading && <SettingsLoadingState t={context.t} />}

        {form && (
          <div className="settings-workspace">
            <SettingsDirectory activeSection={activeSection} setActiveSection={setActiveSection} t={context.t} />

            <div className="settings-section-panel" role="tabpanel">
              <SettingsSectionIntro section={activeSection} t={context.t} />
              {activeSection === "basic" && <ConfigBasicSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "inputs" && <ConfigInputsSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "preprocessing" && <ConfigPreprocessingSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "runtime" && <ConfigRuntimeSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "models" && (
                <ConfigModelProvidersSection
                  form={form}
	                  setForm={setForm}
	                  t={context.t}
	                  probeResults={context.modelProbeResults}
                  pendingAction={modelActionKey(discoverMutation.variables, "discover", discoverMutation.isPending) || modelActionKey(probeMutation.variables, undefined, probeMutation.isPending) || modelActionKey(applyCapabilitiesMutation.variables, "apply", applyCapabilitiesMutation.isPending)}
                  onDiscover={(provider) => discoverMutation.mutate(provider)}
                  onProbe={(provider, level) => probeMutation.mutate({ provider, level })}
                  onApplyCapabilities={(provider, values) => applyCapabilitiesMutation.mutate({ provider, values })}
                />
              )}
              {activeSection === "diagnostics" && <ConfigDiagnosticsPanel diagnostics={diagnosticsQuery.data} loading={diagnosticsQuery.isFetching} t={context.t} />}
              {activeSection === "advanced" && (
                <div className="advanced-yaml-section" id="settings-advanced">
                  <textarea className="config-editor" spellCheck={false} value={context.configContent} onChange={(event) => context.setConfigContent(event.target.value)} />
                  <button className="button primary" onClick={() => yamlSave.mutate()} disabled={saving}>
                    {saving ? context.t("running") : context.t("saveYaml")}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </article>
    </section>
  );
}

type ConfigSectionId = "basic" | "inputs" | "preprocessing" | "runtime" | "models" | "diagnostics" | "advanced";

function modelActionKey(
  variables: unknown,
  forcedAction: "discover" | "minimal" | "structured" | "apply" | undefined,
  pending: boolean,
): string | null {
  if (!pending) return null;
  if (typeof variables === "string") return `${variables}:${forcedAction || "discover"}`;
  if (variables && typeof variables === "object" && "provider" in variables) {
    const record = variables as { provider?: unknown; level?: unknown };
    const provider = typeof record.provider === "string" ? record.provider : "";
    const action = forcedAction || (typeof record.level === "string" ? record.level : "probe");
    return provider ? `${provider}:${action}` : null;
  }
  return null;
}

const CONFIG_SECTIONS: Array<{ id: ConfigSectionId; titleKey: string; copyKey: string }> = [
  { id: "basic", titleKey: "settingsSectionBasic", copyKey: "settingsSectionBasicCopy" },
  { id: "inputs", titleKey: "settingsSectionInputs", copyKey: "settingsSectionInputsCopy" },
  { id: "preprocessing", titleKey: "settingsSectionPreprocessing", copyKey: "settingsSectionPreprocessingCopy" },
  { id: "runtime", titleKey: "settingsSectionRuntime", copyKey: "settingsSectionRuntimeCopy" },
  { id: "models", titleKey: "settingsSectionModels", copyKey: "settingsSectionModelsCopy" },
  { id: "diagnostics", titleKey: "settingsSectionDiagnostics", copyKey: "settingsSectionDiagnosticsCopy" },
  { id: "advanced", titleKey: "advancedYaml", copyKey: "advancedYamlCopy" },
];

const CONFIG_SECTION_GROUPS: Array<{ titleKey: string; items: ConfigSectionId[] }> = [
  { titleKey: "settingsGroupKnowledgeBase", items: ["basic", "inputs", "preprocessing"] },
  { titleKey: "settingsGroupRuntime", items: ["runtime", "models", "diagnostics"] },
  { titleKey: "settingsGroupAdvanced", items: ["advanced"] },
];

function SettingsSectionIntro({ section, t }: { section: ConfigSectionId; t: (key: string) => string }) {
  const item = CONFIG_SECTIONS.find((candidate) => candidate.id === section) || CONFIG_SECTIONS[0];
  return (
    <div className="settings-section-intro">
      <div>
        <p className="eyebrow">{t("settingsDetail")}</p>
        <h2>{t(item.titleKey)}</h2>
        <p className="panel-copy">{t(item.copyKey)}</p>
      </div>
    </div>
  );
}

function SettingsLoadingState({ t }: { t: (key: string) => string }) {
  return (
    <div className="settings-workspace">
      <SettingsDirectory activeSection="basic" setActiveSection={() => undefined} t={t} disabled />
      <div className="settings-section-panel">
        <div className="settings-section-intro">
          <p className="eyebrow">{t("loading")}</p>
          <h2>{t("settingsSectionBasic")}</h2>
          <p className="panel-copy">{t("settingsSectionBasicCopy")}</p>
        </div>
        <div className="form-grid config-basic-grid">
          <div className="skeleton-field" />
          <div className="skeleton-field" />
        </div>
      </div>
    </div>
  );
}

function normalizeConfigForm(form: ConfigForm): ConfigForm {
  return {
    ...form,
    vault_id: form.vault_id || "default",
    vaults:
      form.vaults?.length
        ? form.vaults
        : [
            {
              id: form.vault_id || "default",
              name: form.project_name || "My Knowledge Base",
              path: form.vault_path || "./vaults/all",
              active: true,
            },
          ],
    providers: (form.providers || []).map((provider) => ({
      ...provider,
      adapter: provider.adapter || "openai_compatible",
      verify_tls: provider.verify_tls ?? true,
      tls_ca_file: provider.tls_ca_file || "",
      extra_body: provider.extra_body || {},
    })),
    enabled_connectors: form.enabled_connectors || [],
    markdown_roots: form.markdown_roots || [],
    generic_chat_enabled: Boolean(form.generic_chat_enabled),
    generic_chat_roots: form.generic_chat_roots || [],
    generic_chat_raw_output_dir: form.generic_chat_raw_output_dir || "",
    mineru_parse_method: form.mineru_parse_method || "auto",
    mineru_backend: form.mineru_backend || "pipeline",
    mineru_timeout_seconds: form.mineru_timeout_seconds || 600,
    mineru_patterns: form.mineru_patterns || ["*.pdf", "*.docx", "*.pptx"],
    mineru_recursive: form.mineru_recursive ?? true,
    mineru_return_md: form.mineru_return_md ?? true,
    mineru_return_middle_json: Boolean(form.mineru_return_middle_json),
    mineru_return_model_output: Boolean(form.mineru_return_model_output),
    mineru_return_content_list: Boolean(form.mineru_return_content_list),
    mineru_return_images: Boolean(form.mineru_return_images),
    mineru_response_format_zip: Boolean(form.mineru_response_format_zip),
    mineru_lang_list: form.mineru_lang_list || "ch",
    mineru_formula_enable: form.mineru_formula_enable ?? true,
    mineru_table_enable: form.mineru_table_enable ?? true,
    mineru_server_url: form.mineru_server_url || "",
    mineru_start_page_id: form.mineru_start_page_id ?? 0,
    mineru_end_page_id: form.mineru_end_page_id ?? 99999,
    mineru_extra_fields_json: form.mineru_extra_fields_json || "{}",
  };
}

function SettingsDirectory({
  activeSection,
  disabled = false,
  setActiveSection,
  t,
}: {
  activeSection: ConfigSectionId;
  disabled?: boolean;
  setActiveSection: (section: ConfigSectionId) => void;
  t: (key: string) => string;
}) {
  return (
    <aside className="settings-section-rail" role="tablist" aria-label={t("settingsSections")}>
      <div className="panel-header compact">
        <h2>{t("docsDirectory")}</h2>
      </div>
      {CONFIG_SECTION_GROUPS.map((group) => (
        <section className="docs-group" key={group.titleKey}>
          <h3>{t(group.titleKey)}</h3>
          <div className="docs-link-list">
            {group.items.map((sectionId) => {
              const section = CONFIG_SECTIONS.find((item) => item.id === sectionId) || CONFIG_SECTIONS[0];
              return (
                <button
                  className={`docs-link ${activeSection === section.id ? "active" : ""}`}
                  disabled={disabled}
                  key={section.id}
                  type="button"
                  role="tab"
                  aria-selected={activeSection === section.id}
                  onClick={() => setActiveSection(section.id)}
                >
                  <strong>{t(section.titleKey)}</strong>
                  <span>{t(section.copyKey)}</span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </aside>
  );
}
