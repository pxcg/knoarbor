import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  discoverModelProvider,
  getConfigDiagnostics,
  getConfigForm,
  probeImageProvider,
  saveConfig,
  saveConfigForm,
  type ConfigForm,
  type ImageProviderProbeResponse,
} from "../../api/client";
import type { ConfigAppContext } from "../../appContext";
import { modelActionKey, normalizeConfigForm } from "../../components/config/ConfigPageParts";
import { queryKeys } from "../../queryKeys";

export function useConfigController(context: ConfigAppContext) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ConfigForm | null>(null);
  const [imageProbeResults, setImageProbeResults] = useState<Record<string, ImageProviderProbeResponse>>({});
  const formSaveQueue = useRef<Promise<void>>(Promise.resolve());
  const latestFormSave = useRef<Promise<string | null> | null>(null);
  const preserveLocalForm = useRef(false);

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
    if (formQuery.data && !preserveLocalForm.current) {
      setForm(normalizeConfigForm(formQuery.data));
    }
  }, [formQuery.data]);

  useEffect(() => {
    const error = formQuery.error || diagnosticsQuery.error;
    if (error) console.error("Configuration loading failed", error);
  }, [context, diagnosticsQuery.error, formQuery.error]);

  async function updateSettingsFromDisk() {
    preserveLocalForm.current = false;
    await queryClient.invalidateQueries({ queryKey: queryKeys.configFormRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.configDiagnosticsRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.modelProvidersRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.sourceCatalogRoot });
    await formQuery.refetch();
    await diagnosticsQuery.refetch();
    await context.refreshAll();
  }

  async function saveStructuredFormSnapshot(formSnapshot: ConfigForm): Promise<string | null> {
    const operation = formSaveQueue.current.catch(() => undefined).then(async () => {
      const response = await saveConfigForm(context.configPath, formSnapshot);
      const savedForm = normalizeConfigForm(formSnapshot);
      context.setConfigPath(response.config_path);
      context.setConfigExists(true);
      context.setSummary(response.summary || {});
      preserveLocalForm.current = true;
      queryClient.setQueryData(queryKeys.configForm(response.config_path), savedForm);
      if (response.config_path !== context.configPath) {
        queryClient.setQueryData(queryKeys.configForm(context.configPath), savedForm);
      }
      return response.config_path;
    });
    latestFormSave.current = operation;
    formSaveQueue.current = operation.then(() => undefined, () => undefined);
    return operation;
  }

  async function saveStructuredForm(): Promise<string | null> {
    if (!form) throw new Error("Configuration form is not loaded.");
    return saveStructuredFormSnapshot(form);
  }

  const structuredSave = useMutation({
    mutationFn: saveStructuredForm,
    onSuccess: async () => {
      await updateSettingsFromDisk();
    },
    onError: (error) => console.error("Structured configuration save failed", error),
  });

  const yamlSave = useMutation({
    mutationFn: () => saveConfig(context.configPath, context.configContent),
    onSuccess: async (response) => {
      context.setConfigPath(response.config_path);
      context.setConfigExists(true);
      context.setSummary(response.summary || {});
      await updateSettingsFromDisk();
    },
    onError: (error) => console.error("YAML configuration save failed", error),
  });

  async function awaitPendingFormSaveForModelAction(): Promise<string | null> {
    return latestFormSave.current ? latestFormSave.current : context.configPath;
  }

  async function commitFormSnapshot(formSnapshot: ConfigForm): Promise<void> {
    await saveStructuredFormSnapshot(formSnapshot);
    await queryClient.invalidateQueries({ queryKey: queryKeys.configDiagnosticsRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.modelProvidersRoot });
    await queryClient.invalidateQueries({ queryKey: queryKeys.sourceCatalogRoot });
    await context.refreshAll();
  }

  async function commitModelFormSnapshot(formSnapshot: ConfigForm): Promise<void> {
    await saveStructuredFormSnapshot(formSnapshot);
    void queryClient.invalidateQueries({ queryKey: queryKeys.modelProvidersRoot });
  }

  const discoverMutation = useMutation({
    mutationFn: async (provider: string) => {
      const configPath = await awaitPendingFormSaveForModelAction();
      return discoverModelProvider(configPath, provider);
    },
    onSuccess: (result) => {
      context.setModelProbeResults((current) => ({
        ...current,
        [result.provider]: { ...(current[result.provider] || {}), discovery: result, lastAction: "discover" },
      }));
    },
    onError: (error) => console.error("Model discovery failed", error),
  });

  const imageProbeMutation = useMutation({
    mutationFn: async (provider: string) => {
      const configPath = await awaitPendingFormSaveForModelAction();
      return probeImageProvider(configPath, provider);
    },
    onSuccess: (result) => {
      setImageProbeResults((current) => ({ ...current, [result.provider]: result }));
    },
    onError: (error) => console.error("Image model probe failed", error),
  });

  async function reloadSettings() {
    await updateSettingsFromDisk();
  }

  return {
    diagnosticsQuery,
    form,
    formQuery,
    imagePendingProvider: imageProbeMutation.isPending ? imageProbeMutation.variables || null : null,
    imageProbeResults,
    modelPendingAction: modelActionKey(discoverMutation.variables, "discover", discoverMutation.isPending),
    reloadSettings,
    saving: structuredSave.isPending || yamlSave.isPending,
    commitFormSnapshot,
    commitModelFormSnapshot,
    clearImageProbe: (provider: string) => {
      setImageProbeResults((current) => {
        if (!current[provider]) return current;
        const next = { ...current };
        delete next[provider];
        return next;
      });
    },
    setForm,
    startDiscover: (provider: string) => discoverMutation.mutate(provider),
    startImageProbe: (provider: string) => imageProbeMutation.mutate(provider),
    saveStructured: () => structuredSave.mutate(),
    saveYaml: () => yamlSave.mutate(),
  };
}
