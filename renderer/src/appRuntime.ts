import type { ModelProviderProbeState } from "./api/client";

export function readStoredModelProbeResults(): Record<string, ModelProviderProbeState> {
  try {
    const raw = localStorage.getItem("knoarbor.modelProbeResults");
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}
