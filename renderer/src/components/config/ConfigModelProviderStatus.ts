import type { ConfigFormProvider, ModelProviderProbeState } from "../../api/client";

export type ProviderRuntimeStatus = {
  tone: "ok" | "warning" | "error" | "unknown";
  dotClass: "online" | "warning" | "offline" | "neutral";
  label: string;
  detail: string;
  checked: boolean;
};

export function providerRuntimeStatus(provider: ConfigFormProvider, result: ModelProviderProbeState | undefined, t: (key: string) => string): ProviderRuntimeStatus {
  const latest = currentModelProbeResult(provider, result);
  if (latest) {
    if (latest.status === "ok" && latest.available) {
      return {
        tone: "ok",
        dotClass: "online",
        label: t("modelAvailable"),
        detail: latest.message || provider.model || t("noModelSelected"),
        checked: true,
      };
    }
    if (latest.status === "warning" || latest.available) {
      return {
        tone: "warning",
        dotClass: "warning",
        label: t("modelNeedsAttention"),
        detail: latest.message || provider.model || t("noModelSelected"),
        checked: true,
      };
    }
    return {
      tone: "error",
      dotClass: "offline",
      label: t("modelUnavailable"),
      detail: latest.message || provider.model || t("noModelSelected"),
      checked: true,
    };
  }

  const hasMinimumConfig = Boolean(provider.name && provider.model && provider.base_url);
  if (hasMinimumConfig) {
    return {
      tone: "ok",
      dotClass: "online",
      label: t("modelConfigured"),
      detail: `${provider.model} · ${t("modelConfiguredUnchecked")}`,
      checked: true,
    };
  }

  return {
    tone: "warning",
    dotClass: "warning",
    label: t("modelNotChecked"),
    detail: t("providerMissingRequiredFields"),
    checked: false,
  };
}

function currentModelProbeResult(provider: ConfigFormProvider, result: ModelProviderProbeState | undefined) {
  if (!result) return undefined;
  const discoveryModels = result.discovery?.model_ids || [];
  if (result.discovery && (!provider.model || discoveryModels.includes(provider.model))) return result.discovery;
  return undefined;
}
