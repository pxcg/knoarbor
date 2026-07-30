import { getRun, type ChatCitation, type QueryRawEvidence, type VaultSelector } from "../../api/client";
import type { ChatAppContext } from "../../appContext";
import { pathBaseName } from "../../pathUtils";
import { resolveVaultAssetImageSrc as resolveVaultAssetImageSrcBase } from "../../vaultAssetPaths";

type ChatFollowup = {
  kind: "question" | "page";
  label: string;
  prompt?: string;
  citation?: ChatCitation;
};

export function buildChatFollowups(citations: ChatCitation[], context: ChatAppContext): ChatFollowup[] {
  const pages = uniquePageCitations(citations).filter((citation) => citation.kind === "page" && citation.path);
  if (!pages.length) return [];
  const answerPages = pages.filter((citation) => citation.role !== "source" && !citation.path?.startsWith("sources/"));
  const primary = answerPages.find((citation) => citation.role === "primary") || answerPages[0] || pages[0];
  const supporting = answerPages.filter((citation) => citation.path !== primary.path).slice(0, 2);
  const questions = uniqueFollowups([
    questionForPage(primary, context, "primary"),
    supporting[0] ? relationQuestion(primary, supporting[0], context) : undefined,
    supporting[1] ? relationQuestion(primary, supporting[1], context) : undefined,
  ]).slice(0, 3);
  return questions;
}

export function uniquePageCitations(citations: ChatCitation[]) {
  const seen = new Set<string>();
  const unique: ChatCitation[] = [];
  for (const citation of citations) {
    const key = `${citation.kind}:${citation.vault_id || ""}:${citation.evidence_id || citation.source_unit_id || citation.path || citation.run_id || citation.title || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(citation);
  }
  return unique;
}

export function uniqueFollowups(items: Array<ChatFollowup | undefined>) {
  const seen = new Set<string>();
  const unique: ChatFollowup[] = [];
  for (const item of items) {
    if (!item || seen.has(item.label)) continue;
    seen.add(item.label);
    unique.push(item);
  }
  return unique;
}

export function questionForPage(citation: ChatCitation, context: ChatAppContext, role: "primary" | "supporting"): ChatFollowup {
  const title = citationTitle(citation);
  const isZh = context.language === "zh";
  const looksLikeComparison = /vs|versus|compare|comparison|对比|区别/i.test(title);
  let prompt: string;
  if (looksLikeComparison) {
    prompt = isZh ? `详细总结 ${title} 的主要差异和适用场景` : `Summarize the key differences and use cases in ${title}`;
  } else if (role === "primary") {
    prompt = isZh ? `进一步解释 ${title} 的关键机制和实践要点` : `Explain the key mechanisms and practical takeaways of ${title}`;
  } else {
    prompt = isZh ? `展开讲讲 ${title} 和当前问题的关系` : `Explain how ${title} relates to the current question`;
  }
  return { kind: "question", label: prompt, prompt };
}

export function relationQuestion(primary: ChatCitation, supporting: ChatCitation, context: ChatAppContext): ChatFollowup {
  const primaryTitle = citationTitle(primary);
  const supportingTitle = citationTitle(supporting);
  const prompt = context.language === "zh"
    ? `${primaryTitle} 和 ${supportingTitle} 有什么关系？`
    : `How are ${primaryTitle} and ${supportingTitle} related?`;
  return { kind: "question", label: prompt, prompt };
}

export function citationTitle(citation: ChatCitation) {
  if (citation.title?.trim()) return citation.title.trim();
  if (citation.path?.trim()) {
    const name = pathBaseName(citation.path);
    return name.replace(/\.md$/i, "").replace(/-/g, " ");
  }
  return citation.source_unit_id || citation.run_id || citation.kind;
}

export function groupCitations(citations: ChatCitation[], context: ChatAppContext) {
  const indexed = collapseRawCitations(citations);
  const groups = new Map<string, { key: string; label: string; items: typeof indexed }>();
  for (const item of indexed) {
    const key = citationDocumentKey(item.citation);
    const existing = groups.get(key);
    if (existing) {
      existing.items.push(item);
      continue;
    }
    groups.set(key, {
      key,
      label: citationDocumentLabel(item.citation, context),
      items: [item],
    });
  }
  return Array.from(groups.values());
}

export function relatedCitationsForRaw(citation: ChatCitation, citations: ChatCitation[]) {
  if (citation.kind !== "raw_evidence") return [citation];
  const key = rawCitationKey(citation);
  return citations.filter((item) => item.kind === "raw_evidence" && rawCitationKey(item) === key);
}

function collapseRawCitations(citations: ChatCitation[]) {
  const items: Array<{
    citation: ChatCitation;
    index: number;
    relatedCitations: ChatCitation[];
  }> = [];
  const rawItems = new Map<string, (typeof items)[number]>();
  citations.forEach((citation, index) => {
    if (citation.kind !== "raw_evidence") {
      items.push({ citation, index, relatedCitations: [citation] });
      return;
    }
    const key = rawCitationKey(citation);
    const existing = rawItems.get(key);
    if (existing) {
      existing.relatedCitations.push(citation);
      return;
    }
    const item = { citation, index, relatedCitations: [citation] };
    rawItems.set(key, item);
    items.push(item);
  });
  return items;
}

function rawCitationKey(citation: ChatCitation) {
  const vault = citation.vault_id || citation.vault_path || "";
  const rawIdentity = citation.source_unit_id
    || citation.evidence_id
    || [
      citation.raw_revision_id || citation.path || "",
      citation.title || "",
      citation.char_start ?? "",
      citation.char_end ?? "",
    ].join(":");
  return `${vault}:raw:${rawIdentity}`;
}

export function citationDocumentKey(citation: ChatCitation) {
  const vault = citation.vault_id || citation.vault_path || "";
  if (citation.path) return `${vault}:path:${citation.path}`;
  if (citation.raw_revision_id) return `${vault}:raw:${citation.raw_revision_id}`;
  return `${vault}:${citation.kind}:${citation.run_id || citation.evidence_id || citation.source_unit_id || citation.title || ""}`;
}

export function sameCitationDocument(left: ChatCitation, right: ChatCitation) {
  return citationDocumentKey(left) === citationDocumentKey(right);
}

export function citationDocumentLabel(citation: ChatCitation, context: ChatAppContext) {
  if (citation.kind === "raw_evidence" && citation.path) {
    const name = pathBaseName(citation.path)
      .replace(/\.md$/i, "")
      .replace(/--[a-f0-9]{8,}$/i, "")
      .replace(/[-_]+/g, " ")
      .trim();
    if (name) return name;
  }
  return citationTitle(citation) || context.t("chatEvidenceSource");
}

export function citationExcerpt(citation: ChatCitation, evidenceItems: QueryRawEvidence[]) {
  const evidence = citation.evidence_id
    ? evidenceItems.find((item) => item.evidence_id === citation.evidence_id)
    : evidenceItems.find((item) => item.source_unit_id === citation.source_unit_id);
  if (!evidence) return citation.reason || "";
  if (
    evidence.content
    && typeof evidence.source_unit_char_start === "number"
    && typeof citation.char_start === "number"
    && typeof citation.char_end === "number"
  ) {
    const start = citation.char_start - evidence.source_unit_char_start;
    const end = citation.char_end - evidence.source_unit_char_start;
    if (start >= 0 && end > start && end <= evidence.content.length) {
      return evidence.content.slice(start, end).trim();
    }
  }
  return evidence.excerpt?.trim() || citation.reason || "";
}

export function citationSpanCount(citation: ChatCitation) {
  return citation.spans?.length || (
    typeof citation.char_start === "number" && typeof citation.char_end === "number"
      ? 1
      : 1
  );
}

export function citationSelector(citation: ChatCitation, context: ChatAppContext): VaultSelector {
  return {
    config_path: context.chatScopeVaultSelector.config_path,
    vault_id: citation.vault_id || context.chatScopeVaultSelector.vault_id,
    vault_path: citation.vault_id ? undefined : citation.vault_path || context.chatScopeVaultSelector.vault_path,
  };
}

export function followupPromptForCitation(citation: ChatCitation, context: ChatAppContext) {
  const title = citationTitle(citation);
  return context.language === "zh"
    ? `围绕 ${title} 继续展开，结合这页内容讲清楚关键机制和实践要点`
    : `Continue with ${title}; explain the key mechanisms and practical takeaways from this page.`;
}

export async function openCitationTarget(citation: ChatCitation, context: ChatAppContext) {
  if (citation.kind === "page" && citation.path) {
    context.openWikiPageInVault(citation.vault_id, citation.path);
    return;
  }
  if (citation.kind === "report" && citation.path) {
    if (!citation.vault_id) throw new Error("Report citation is missing its knowledge-base identity.");
    context.openReport(citation.path, citation.vault_id);
    return;
  }
  if (citation.kind === "run") {
    if (!citation.run_id) return;
    if (!citation.vault_id) throw new Error("Run citation is missing its knowledge-base identity.");
    const selector = citationSelector(citation, context);
    const run = await getRun(selector, citation.run_id);
    if (!run.vault_id) throw new Error("Run record is missing its knowledge-base identity.");
    context.openRun(run.run_id, run.vault_id, run.flow);
  }
}

export function resolveChatImageSrc(src: string | undefined, citations: ChatCitation[], context: ChatAppContext): string | undefined {
  const citationVaultPath =
    citations.find((citation) => citation.vault_path)?.vault_path ||
    citations
      .map((citation) => {
        if (!citation.vault_id) return undefined;
        return context.vaultOptions.find((vault) => vault.id === citation.vault_id)?.path;
      })
      .find((path): path is string => Boolean(path));
  return resolveVaultAssetImageSrc(src, citationVaultPath || context.chatScopeVaultSelector.vault_path || context.vaultPath);
}

export function resolveVaultAssetImageSrc(src: string | undefined, vaultPath: string | undefined): string | undefined {
  return resolveVaultAssetImageSrcBase(src, vaultPath);
}

export type ChatErrorPresentation = {
  message: string;
  action: "settings" | "none";
};

export function chatErrorPresentation(error: unknown, context: ChatAppContext): ChatErrorPresentation {
  const message = error instanceof Error ? error.message : String(error);
  const code = _chatErrorField(error, "code") || _errorCodeFromMessage(message);
  const stage = _chatErrorField(error, "stage");
  const lower = message.toLowerCase();
  if (code === "KA-MODEL-001" || code === "KA-SEM-001") {
    return { message: context.t("chatErrorInvalidOutput"), action: "none" };
  }
  if (stage === "retrieving") {
    return { message: context.t("chatErrorRetrieval"), action: "none" };
  }
  if (code === "KA-STORAGE-001") {
    return { message: context.t("chatErrorStorage"), action: "none" };
  }
  if (code === "KA-VAULT-001" || lower.includes("selected knowledge base")) {
    return { message: context.t("chatErrorVaultUnavailable"), action: "settings" };
  }
  if (code === "KA-EXT-001") {
    return { message: context.t("chatErrorModelUnavailable"), action: "settings" };
  }
  if (lower.includes("invalid decision") || lower.includes("invalid json") || lower.includes("model_output")) {
    return { message: context.t("chatErrorInvalidOutput"), action: "none" };
  }
  return { message: context.t("chatErrorService"), action: "none" };
}

export function readableChatError(error: unknown, context: ChatAppContext): string {
  return chatErrorPresentation(error, context).message;
}

function _chatErrorField(error: unknown, field: "code" | "stage"): string {
  if (typeof error !== "object" || error === null) return "";
  const value = (error as Record<string, unknown>)[field];
  return typeof value === "string" ? value : "";
}

function _errorCodeFromMessage(message: string): string {
  return /\[(KA-[A-Z]+-\d+)\]/.exec(message)?.[1] || "";
}
