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
import type { AppContext } from "../appContext";
import { ConfigDiagnosticsPanel } from "../components/config/ConfigDiagnosticsPanel";
import {
  ConfigGeneralSection,
  SettingsDirectory,
  SettingsLoadingState,
  SettingsSectionIntro,
  modelActionKey,
  normalizeConfigForm,
  type ConfigSectionId,
} from "../components/config/ConfigPageParts";
import {
  ConfigBasicSection,
  ConfigInputsSection,
  ConfigPreprocessingSection,
  ConfigRuntimeSection,
} from "../components/config/ConfigSettingsSections";
import { ConfigModelProvidersSection } from "../components/config/ConfigModelProvidersSection";

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
        {formQuery.isLoading && <SettingsLoadingState t={context.t} />}

        {form && (
          <div className="settings-workspace">
            <SettingsDirectory activeSection={activeSection} setActiveSection={setActiveSection} t={context.t} />

            <div className="settings-section-panel" role="tabpanel">
              <SettingsSectionIntro
                section={activeSection}
                t={context.t}
                saving={saving}
                canSave={Boolean(form)}
                onSave={() => structuredSave.mutate()}
                onReload={async () => {
                  await updateSettingsFromDisk();
                  context.setNotice({ message: context.t("refreshComplete") });
                }}
                reloading={formQuery.isFetching || diagnosticsQuery.isFetching}
              />
              {activeSection === "basic" && <ConfigBasicSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "general" && <ConfigGeneralSection context={context} />}
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
