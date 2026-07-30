import {
  readChatSession,
  type ChatCitation,
  type ChatResponse,
  type ChatAnswerProvenance,
  type QueryRawEvidence,
  type ChatStreamEvent,
  type ModelProviderSummary,
  type PageDetail,
} from "../../api/client";
import type { ChatAppContext } from "../../appContext";
import { currentModelProbeAssessment } from "../../modelProbeRuntime";

export type ChatTurn = {
  turnId?: string;
  messageId?: string;
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
  rawEvidence?: QueryRawEvidence[];
  hiddenEvidenceCount?: number;
  citationWarnings?: string[];
  kind?: "answer" | "error" | "status";
  errorAction?: "settings" | "none";
  streaming?: boolean;
  answerProvenance?: ChatAnswerProvenance;
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
  highlightTerm: string | null;
  highlightTerms: string[];
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
  return compact;
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

export function chatStageLabel(stage: ChatRequestStage, context: ChatAppContext) {
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

export function chatProviderStatus(providerName: string, providers: ModelProviderSummary[], context: ChatAppContext) {
  const provider = providers.find((item) => item.name === providerName);
  if (!provider) return "unknown";
  const result = currentModelProbeResult(provider, context.modelProbeResults[provider.name]);
  if (!result) return "unknown";
  if (result.status === "ok" && result.available) return "ok";
  if (result.status === "warning" || result.available) return "warning";
  return "error";
}

export function chatProviderStatusLabel(providerName: string, context: ChatAppContext) {
  const provider = context.modelProviders?.providers.find((item) => item.name === providerName);
  if (!provider) return context.t("modelNotChecked");
  const result = currentModelProbeResult(provider, context.modelProbeResults[provider.name]);
  if (!result) {
    return context.t("modelNotChecked");
  }
  if (result.status === "ok" && result.available) return context.t("modelAvailable");
  if (result.status === "warning" || result.available) return context.t("modelNeedsAttention");
  return context.t("modelUnavailable");
}

export function currentModelProbeResult(provider: ModelProviderSummary, result: ChatAppContext["modelProbeResults"][string]) {
  const assessment = currentModelProbeAssessment(result?.discovery, provider.model);
  if (!assessment) return undefined;
  return {
    ...assessment.discovery,
    configured_model_found: assessment.configuredModelFound,
    status: assessment.status,
  };
}

export function sessionRecordToTurns(record: Awaited<ReturnType<typeof readChatSession>>): ChatTurn[] {
  if (record.turns?.length) {
    return record.turns.flatMap((turn) => [
      { role: "user" as const, content: turn.user_message.content, turnId: turn.turn_id, messageId: turn.user_message.message_id },
      {
        role: "assistant" as const,
        content: turn.assistant_message.content,
        turnId: turn.turn_id,
        messageId: turn.assistant_message.message_id,
        citations: turn.citations || [],
        rawEvidence: rawEvidenceFromToolTrace(turn.tool_trace || []),
        hiddenEvidenceCount: turn.hidden_evidence_count || 0,
        citationWarnings: turn.citation_warnings || [],
        answerProvenance: turn.answer_provenance,
      },
    ]);
  }
  return record.messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      role: message.role === "assistant" ? "assistant" : "user",
      content: message.content,
      citations: message.role === "assistant" ? record.citations : undefined,
      rawEvidence: message.role === "assistant" ? rawEvidenceFromToolTrace(record.tool_trace || []) : undefined,
      hiddenEvidenceCount: message.role === "assistant" ? record.hidden_evidence_count || 0 : undefined,
      citationWarnings: message.role === "assistant" ? record.citation_warnings || [] : undefined,
    }));
}

export function rawEvidenceFromChatResponse(response: ChatResponse): QueryRawEvidence[] {
  return rawEvidenceFromToolTrace(response.tool_trace || []);
}

export function evidenceForCitation(
  citation: ChatCitation,
  evidenceItems: QueryRawEvidence[],
): QueryRawEvidence | undefined {
  if (citation.evidence_id) {
    return evidenceItems.find((item) => item.evidence_id === citation.evidence_id);
  }
  if (citation.source_unit_id) {
    return evidenceItems.find((item) => item.source_unit_id === citation.source_unit_id);
  }
  return undefined;
}

export function rawEvidenceFromToolTrace(toolTrace: Array<{ result?: Record<string, unknown> }>): QueryRawEvidence[] {
  const seen = new Set<string>();
  const items: QueryRawEvidence[] = [];
  for (const trace of toolTrace) {
    const rawEvidence = Array.isArray(trace.result?.raw_evidence) ? trace.result.raw_evidence : [];
    for (const rawItem of rawEvidence) {
      if (!isRawEvidence(rawItem)) continue;
      const key = rawItem.evidence_id || rawItem.source_unit_id;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push(rawItem);
    }
  }
  return items;
}

function isRawEvidence(value: unknown): value is QueryRawEvidence {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.evidence_id === "string"
    && typeof item.raw_record_id === "string"
    && typeof item.raw_revision_id === "string"
    && typeof item.source_unit_id === "string"
    && typeof item.source_record_id === "string"
    && typeof item.excerpt === "string"
  );
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
