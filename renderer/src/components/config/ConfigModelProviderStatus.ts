import type { ConfigFormProvider, ModelProviderProbeState } from "../../api/client";
import { currentModelProbeAssessment } from "../../modelProbeRuntime";

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
        detail: provider.model || t("noModelSelected"),
        checked: true,
      };
    }
    if (latest.status === "warning" || latest.available) {
      return {
        tone: "warning",
        dotClass: "warning",
        label: t("modelNeedsAttention"),
        detail: t("modelNeedsAttention"),
        checked: true,
      };
    }
    return {
      tone: "error",
      dotClass: "offline",
      label: t("modelUnavailable"),
      detail: t("modelUnavailable"),
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
  const assessment = currentModelProbeAssessment(result?.discovery, provider.model);
  if (!assessment) return undefined;
  return {
    ...assessment.discovery,
    configured_model_found: assessment.configuredModelFound,
    status: assessment.status,
  };
}
