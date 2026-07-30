import { requestJson } from "./http";
import type {
  DoctorReport,
  GraphResponse,
  HealthResponse,
  TokenAnalysis,
  UiStatusResponse,
} from "./types";

export async function getHealth(): Promise<HealthResponse> {
  return requestJson("/health");
}

export async function getDoctor(
  configPath?: string | null,
  options: { checkModelRuntime?: boolean; checkConnectorRuntime?: boolean } = {},
): Promise<DoctorReport> {
  const params = new URLSearchParams();
  if (configPath) params.set("config_path", configPath);
  if (options.checkModelRuntime === false) params.set("check_model_runtime", "false");
  if (options.checkConnectorRuntime === false) params.set("check_connector_runtime", "false");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson(`/doctor${suffix}`);
}

export async function getStatus(vaultPath: string): Promise<UiStatusResponse> {
  return requestJson(`/vaults/status?vault_path=${encodeURIComponent(vaultPath)}`);
}

export async function getGraph(vaultPath: string): Promise<GraphResponse> {
  return requestJson(`/wiki/graph?vault_path=${encodeURIComponent(vaultPath)}`);
}

export async function getTokenAnalysis(vaultPath: string, limit = 5000): Promise<TokenAnalysis> {
  return requestJson(`/tokens?vault_path=${encodeURIComponent(vaultPath)}&limit=${limit}`);
}
