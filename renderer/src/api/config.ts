import {
  hasDesktopConfigBridge,
  writeDesktopConfigForm,
  writeDesktopConfigRaw,
} from "../desktop/desktopBridge";
import { requestJson } from "./http";
import type {
  ConfigForm,
  ConfigDiagnostics,
  ImageProviderProbeResponse,
  ModelApplyCapabilitiesResponse,
  ModelCapabilitySuggestion,
  ModelDiscoveryResponse,
  ModelProvidersResponse,
  SourceCatalogResponse,
  UiConfigResponse,
  UiConfigUpdateResponse,
  VaultListResponse,
} from "./types";

export async function getConfig(): Promise<UiConfigResponse> {
  return requestJson("/config");
}

export async function getVaults(configPath?: string | null): Promise<VaultListResponse> {
  const params = new URLSearchParams();
  if (configPath) params.set("config_path", configPath);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/vaults${suffix}`);
}

export async function saveConfig(configPath: string | null, content: string): Promise<UiConfigUpdateResponse> {
  if (hasDesktopConfigBridge()) {
    return (await writeDesktopConfigRaw(configPath, content)) as UiConfigUpdateResponse;
  }
  return requestJson("/config", {
    method: "PUT",
    body: { config_path: configPath, content },
  });
}

export async function getConfigForm(configPath?: string | null): Promise<ConfigForm> {
  const suffix = configPath ? `?config_path=${encodeURIComponent(configPath)}` : "";
  return requestJson(`/config/form${suffix}`);
}

export async function getModelProviders(configPath?: string | null): Promise<ModelProvidersResponse> {
  const suffix = configPath ? `?config_path=${encodeURIComponent(configPath)}` : "";
  return requestJson(`/models/providers${suffix}`);
}

export async function getConfigDiagnostics(
  configPath?: string | null,
  options: { refreshSourceCounts?: boolean } = {},
): Promise<ConfigDiagnostics> {
  const params = new URLSearchParams();
  if (configPath) params.set("config_path", configPath);
  if (options.refreshSourceCounts) params.set("refresh_source_counts", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/config/diagnostics${suffix}`);
}

export async function getSourceCatalog(configPath?: string | null, connectors: string[] = []): Promise<SourceCatalogResponse> {
  const params = new URLSearchParams();
  if (configPath) params.set("config_path", configPath);
  for (const connector of connectors) params.append("connector", connector);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/sources${suffix}`);
}

export async function saveConfigForm(configPath: string | null, form: ConfigForm): Promise<UiConfigUpdateResponse> {
  const { diagnostics: _diagnostics, ...payload } = form;
  if (hasDesktopConfigBridge()) {
    return (await writeDesktopConfigForm(configPath, payload)) as UiConfigUpdateResponse;
  }
  return requestJson("/config/form", {
    method: "PUT",
    body: { ...payload, config_path: configPath },
  });
}

export async function discoverModelProvider(configPath: string | null, provider: string): Promise<ModelDiscoveryResponse> {
  return requestJson("/models/discover", {
    method: "POST",
    body: { config_path: configPath, provider },
  });
}

export async function probeImageProvider(configPath: string | null, provider: string): Promise<ImageProviderProbeResponse> {
  return requestJson("/models/image-probe", {
    method: "POST",
    body: { config_path: configPath, provider },
  });
}

export async function applyModelCapabilities(
  configPath: string | null,
  provider: string,
  values: ModelCapabilitySuggestion,
): Promise<ModelApplyCapabilitiesResponse> {
  return requestJson("/models/apply-capabilities", {
    method: "POST",
    body: {
      config_path: configPath,
      provider,
      context_window: values.context_window ?? null,
      max_output_tokens: values.max_output_tokens ?? null,
      json_mode: values.json_mode ?? null,
    },
  });
}

