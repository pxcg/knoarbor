import {
  readChatSession,
  type ChatCitation,
  type ChatStreamEvent,
  type ModelProviderSummary,
  type PageDetail,
} from "../../api/client";
import type { AppContext } from "../../appContext";

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
  hiddenEvidenceCount?: number;
  citationWarnings?: string[];
  kind?: "answer" | "error" | "status";
  streaming?: boolean;
};

export type ChatFollowup = {
  kind: "question" | "page";
  label: string;
  prompt?: string;
  citation?: ChatCitation;
};

export type ChatRequestStage = "idle" | "preparing" | "retrieving" | "generating" | "waiting_model" | "regenerating";

export type ChatCitationPreview = {
  citation: ChatCitation;
  page: PageDetail | null;
  loading: boolean;
  error: string | null;
};

export function selectedTextOrNull(): string | null {
  if (typeof window === "undefined") return null;
  const selected = window.getSelection()?.toString().trim();
  return selected || null;
}

export function selectedTextOrTurnContent(content: string): string {
  return selectedTextOrNull() || content.trim();
}

export function buildExcerptTitle(content: string): string {
  const compact = content
    .replace(/\s+/g, " ")
    .replace(/^#+\s*/, "")
    .trim();
  if (!compact) return "Chat excerpt";
  return compact.length > 48 ? `${compact.slice(0, 48)}...` : compact;
}

export function appendStreamingAssistantDelta(turns: ChatTurn[], delta: string): ChatTurn[] {
  const lastIndex = turns.length - 1;
  const last = turns[lastIndex];
  if (!last || last.role !== "assistant" || !last.streaming) {
    return [...turns, { role: "assistant", content: delta, streaming: true }];
  }
  return [
    ...turns.slice(0, lastIndex),
    { ...last, content: `${last.content}${delta}` },
  ];
}

export function replaceStreamingAssistant(turns: ChatTurn[], replacement: ChatTurn): ChatTurn[] {
  const lastIndex = turns.length - 1;
  const last = turns[lastIndex];
  if (!last || last.role !== "assistant" || !last.streaming) return [...turns, replacement];
  return [...turns.slice(0, lastIndex), replacement];
}

export function chatStageLabel(stage: ChatRequestStage, context: AppContext) {
  if (stage === "regenerating") return context.t("chatStageRegenerating");
  if (stage === "retrieving") return context.t("chatStageRetrieving");
  if (stage === "generating") return context.t("chatStageGenerating");
  if (stage === "waiting_model") return context.t("chatStageWaitingModel");
  return context.t("chatStagePreparing");
}

export function chatStageFromStreamEvent(event: ChatStreamEvent): ChatRequestStage | null {
  if (event.event === "final") return "generating";
  if (event.event === "error") return "idle";
  if (event.stage === "planning" || event.stage === "preparing") return "preparing";
  if (event.stage === "retrieving") return "retrieving";
  if (event.stage === "generating") return "waiting_model";
  if (event.stage === "completed") return "generating";
  if (event.tool) return "retrieving";
  return null;
}

export function selectedProviderName(selected: string, defaultProvider: string | null | undefined, providers: ModelProviderSummary[]) {
  if (selected && providers.some((provider) => provider.name === selected)) return selected;
  if (defaultProvider && providers.some((provider) => provider.name === defaultProvider)) return defaultProvider;
  return providers[0]?.name || "";
}

export function modelProviderOptionLabel(provider: ModelProviderSummary) {
  return provider.name;
}

export function chatProviderStatus(providerName: string, providers: ModelProviderSummary[], context: AppContext) {
  const provider = providers.find((item) => item.name === providerName);
  if (!provider) return "unknown";
  const result = currentModelProbeResult(provider, context.modelProbeResults[provider.name]);
  if (!result) return provider.api_key_env && !provider.api_key_configured ? "error" : "unknown";
  if (result.status === "ok" && result.available) return "ok";
  if (result.status === "warning" || result.available) return "warning";
  return "error";
}

export function chatProviderStatusLabel(providerName: string, context: AppContext) {
  const provider = context.modelProviders?.providers.find((item) => item.name === providerName);
  if (!provider) return context.t("modelNotChecked");
  const result = currentModelProbeResult(provider, context.modelProbeResults[provider.name]);
  if (!result) {
    if (provider.api_key_env && !provider.api_key_configured) return context.t("envMissing");
    return context.t("modelNotChecked");
  }
  if (result.status === "ok" && result.available) return context.t("modelAvailable");
  if (result.status === "warning" || result.available) return context.t("modelNeedsAttention");
  return context.t("modelUnavailable");
}

export function currentModelProbeResult(provider: ModelProviderSummary, result: AppContext["modelProbeResults"][string]) {
  if (!result) return undefined;
  if (result.probe?.model === provider.model) return result.probe;
  const discoveryModels = result.discovery?.model_ids || [];
  if (result.discovery && (!provider.model || discoveryModels.includes(provider.model))) return result.discovery;
  return undefined;
}

export function sessionRecordToTurns(record: Awaited<ReturnType<typeof readChatSession>>): ChatTurn[] {
  if (record.turns?.length) {
    return record.turns.flatMap((turn) => [
      { role: "user" as const, content: turn.user_message.content },
      {
        role: "assistant" as const,
        content: turn.assistant_message.content,
        citations: turn.citations || [],
        hiddenEvidenceCount: turn.hidden_evidence_count || 0,
        citationWarnings: turn.citation_warnings || [],
      },
    ]);
  }
  return record.messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      role: message.role === "assistant" ? "assistant" : "user",
      content: message.content,
      citations: message.role === "assistant" ? record.citations : undefined,
      hiddenEvidenceCount: message.role === "assistant" ? record.hidden_evidence_count || 0 : undefined,
      citationWarnings: message.role === "assistant" ? record.citation_warnings || [] : undefined,
    }));
}

export function latestAssistantTurnIndex(turns: ChatTurn[]) {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    if (turns[index].role === "assistant" && turns[index].kind !== "error" && turns[index].kind !== "status") return index;
  }
  return -1;
}

export function formatSessionDate(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function renderInlineCitations(content: string, citationCount: number) {
  if (!citationCount) return content;
  return content.replace(/\[(\d+)\]/g, (match, rawIndex: string) => {
    const citationIndex = Number(rawIndex) - 1;
    if (!Number.isInteger(citationIndex) || citationIndex < 0 || citationIndex >= citationCount) return match;
    return `[[${rawIndex}]](#knoarbor-citation=${citationIndex})`;
  });
}
