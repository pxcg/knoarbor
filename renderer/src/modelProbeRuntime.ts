import type { ModelDiscoveryResponse } from "./api/client";

export type CurrentModelProbeAssessment = {
  discovery: ModelDiscoveryResponse;
  configuredModelFound: boolean | null;
  status: ModelDiscoveryResponse["status"];
};

export function currentModelProbeAssessment(
  discovery: ModelDiscoveryResponse | undefined,
  configuredModel: string | null | undefined,
): CurrentModelProbeAssessment | undefined {
  if (!discovery) return undefined;
  const model = configuredModel?.trim() || "";
  if (!model) {
    return { discovery, configuredModelFound: null, status: discovery.status };
  }
  if (model === discovery.model) {
    return {
      discovery,
      configuredModelFound: discovery.configured_model_found ?? null,
      status: discovery.status,
    };
  }
  if (!discovery.model_ids.includes(model)) return undefined;
  return {
    discovery,
    configuredModelFound: true,
    status: discovery.available ? "ok" : discovery.status,
  };
}
