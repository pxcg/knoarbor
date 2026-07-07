import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  discoverModelProvider,
  getConfigDiagnostics,
  getConfigForm,
  saveConfig,
  saveConfigForm,
  type ConfigForm,
} from "../../api/client";
import type { AppContext } from "../../appContext";
import { modelActionKey, normalizeConfigForm } from "../../components/config/ConfigPageParts";
import { queryKeys } from "../../queryKeys";

export function useConfigController(context: AppContext) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ConfigForm | null>(null);

  const formQuery = useQuery({
    queryKey: queryKeys.configForm(context.configPath),
    queryFn: () => getConfigForm(context.configPath),
    staleTime: 5 * 60_000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  const diagnosticsQuery = useQuery({
    queryKey: queryKeys.configDiagnostics(context.configPath),
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
    await queryClient.invalidateQueries({ queryKey: queryKeys.configFormRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.configDiagnosticsRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.modelProvidersRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.sourceCatalogRoot });
    await formQuery.refetch();
    await diagnosticsQuery.refetch();
    await context.refreshAll();
  }

  async function syncStructuredFormFromDisk(configPath: string | null): Promise<void> {
    const refreshed = normalizeConfigForm(await getConfigForm(configPath));
    queryClient.setQueryData(queryKeys.configForm(configPath), refreshed);
    if (configPath !== context.configPath) {
      queryClient.setQueryData(queryKeys.configForm(context.configPath), refreshed);
    }
    setForm(refreshed);
  }

  async function saveStructuredFormSnapshot(formSnapshot: ConfigForm): Promise<string | null> {
    const response = await saveConfigForm(context.configPath, formSnapshot);
    context.setConfigPath(response.config_path);
    context.setConfigExists(true);
    context.setSummary(response.summary || {});
    await syncStructuredFormFromDisk(response.config_path);
    return response.config_path;
  }

  async function saveStructuredForm(): Promise<string | null> {
    if (!form) throw new Error("Configuration form is not loaded.");
    return saveStructuredFormSnapshot(form);
  }

  const structuredSave = useMutation({
    mutationFn: saveStructuredForm,
    onSuccess: async (configPath) => {
      await updateSettingsFromDisk();
      context.setNotice({ message: `${context.t("configurationSaved")} ${configPath || context.configPath}` });
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

  async function saveCurrentFormForModelAction(): Promise<string | null> {
    const configPath = await saveStructuredForm();
    await queryClient.invalidateQueries({ queryKey: queryKeys.configFormRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.configDiagnosticsRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.modelProvidersRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.sourceCatalogRoot });
    return configPath;
  }

  async function commitFormSnapshot(formSnapshot: ConfigForm): Promise<void> {
    await saveStructuredFormSnapshot(formSnapshot);
    await queryClient.invalidateQueries({ queryKey: queryKeys.configFormRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.configDiagnosticsRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.modelProvidersRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.sourceCatalogRoot });
    await context.refreshAll();
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

  async function reloadSettings() {
    await updateSettingsFromDisk();
    context.setNotice({ message: context.t("refreshComplete") });
  }

  return {
    diagnosticsQuery,
    form,
    formQuery,
    modelPendingAction: modelActionKey(discoverMutation.variables, "discover", discoverMutation.isPending),
    reloadSettings,
    saving: structuredSave.isPending || yamlSave.isPending,
    commitFormSnapshot,
    setForm,
    startDiscover: (provider: string) => discoverMutation.mutate(provider),
    saveStructured: () => structuredSave.mutate(),
    saveYaml: () => yamlSave.mutate(),
  };
}
