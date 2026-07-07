import type { ChatCitation, VaultSelector } from "../../api/client";
import type { AppContext } from "../../appContext";
import { pathBaseName } from "../../pathUtils";

type ChatFollowup = {
  kind: "question" | "page";
  label: string;
  prompt?: string;
  citation?: ChatCitation;
};

export function buildChatFollowups(citations: ChatCitation[], context: AppContext): ChatFollowup[] {
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
    const key = `${citation.kind}:${citation.vault_id || ""}:${citation.path || citation.run_id || citation.title || ""}`;
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

export function questionForPage(citation: ChatCitation, context: AppContext, role: "primary" | "supporting"): ChatFollowup {
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

export function relationQuestion(primary: ChatCitation, supporting: ChatCitation, context: AppContext): ChatFollowup {
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
  return citation.run_id || citation.kind;
}

export function groupCitations(citations: ChatCitation[], context: AppContext) {
  const indexed = citations.map((citation, index) => ({ citation, index }));
  const specs = [
    { role: "primary", label: context.t("chatEvidencePrimary") },
    { role: "supporting", label: context.t("chatEvidenceSupporting") },
    { role: "source", label: context.t("chatEvidenceSource") },
  ];
  const groups = specs
    .map((spec) => ({
      label: spec.label,
      items: indexed.filter(({ citation }) => citation.role === spec.role || (!citation.role && spec.role === "supporting")),
    }))
    .filter((group) => group.items.length);
  const groupedIndexes = new Set(groups.flatMap((group) => group.items.map((item) => item.index)));
  const other = indexed.filter((item) => !groupedIndexes.has(item.index));
  if (other.length) groups.push({ label: context.t("chatEvidenceOther"), items: other });
  return groups;
}

export function citationSelector(citation: ChatCitation, context: AppContext): VaultSelector {
  return {
    config_path: context.activeVaultSelector.config_path,
    vault_id: citation.vault_id || context.activeVaultSelector.vault_id,
    vault_path: citation.vault_id ? undefined : citation.vault_path || context.activeVaultSelector.vault_path,
  };
}

export function followupPromptForCitation(citation: ChatCitation, context: AppContext) {
  const title = citationTitle(citation);
  return context.language === "zh"
    ? `围绕 ${title} 继续展开，结合这页内容讲清楚关键机制和实践要点`
    : `Continue with ${title}; explain the key mechanisms and practical takeaways from this page.`;
}

export function openCitationTarget(citation: ChatCitation, context: AppContext) {
  if (citation.kind === "page" && citation.path) {
    context.openWikiPageInVault(citation.vault_id, citation.path);
    return;
  }
  if (citation.kind === "report" && citation.path) {
    context.openReport(citation.path);
    return;
  }
  if (citation.kind === "run") {
    context.navigate("reports");
  }
}

export function resolveChatImageSrc(src: string | undefined, citations: ChatCitation[], context: AppContext): string | undefined {
  const citationVaultPath =
    citations.find((citation) => citation.vault_path)?.vault_path ||
    citations
      .map((citation) => {
        if (!citation.vault_id) return undefined;
        return context.vaultOptions.find((vault) => vault.id === citation.vault_id)?.path;
      })
      .find((path): path is string => Boolean(path));
  return resolveVaultAssetImageSrc(src, citationVaultPath || context.activeVaultSelector.vault_path || context.vaultPath);
}

export function resolveVaultAssetImageSrc(src: string | undefined, vaultPath: string | undefined): string | undefined {
  if (!src) return src;
  const existingVaultAssetPath = vaultAssetPathFromApiSrc(src);
  if (existingVaultAssetPath && vaultPath) {
    return `/ui/api/vault-assets/${encodeURIComponent(existingVaultAssetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
  }
  if (/^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("//") || src.startsWith("/")) return src;
  const assetPath = vaultAssetPathFromSrc(src);
  if (!assetPath || !vaultPath) return src;
  return `/ui/api/vault-assets/${encodeURIComponent(assetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
}

function vaultAssetPathFromApiSrc(src: string): string | null {
  let pathname = src;
  try {
    pathname = new URL(src, "http://knoarbor.local").pathname;
  } catch {
    pathname = src.split("?", 1)[0];
  }
  const prefix = "/ui/api/vault-assets/";
  if (!pathname.startsWith(prefix)) return null;
  const encoded = pathname.slice(prefix.length);
  if (!encoded) return null;
  try {
    return decodeURIComponent(encoded);
  } catch {
    return encoded;
  }
}

export function vaultAssetPathFromSrc(src: string): string | null {
  let cleaned = src.replace(/\\/g, "/").replace(/^\.\//, "");
  if (cleaned.startsWith("../assets/")) cleaned = cleaned.slice("../assets/".length);
  else if (cleaned.startsWith("raw/assets/")) cleaned = cleaned.slice("raw/assets/".length);
  else if (cleaned.startsWith("assets/")) cleaned = cleaned.slice("assets/".length);
  if (/^(images|media|pages|tables)\//.test(cleaned)) return cleaned;
  return null;
}

export function readableChatError(message: string, context: AppContext): string {
  const lower = message.toLowerCase();
  if (lower.includes("invalid decision") || lower.includes("invalid json") || lower.includes("model_output")) {
    return context.t("chatErrorInvalidOutput");
  }
  if (
    lower.includes("model provider")
    || lower.includes("external_service")
    || lower.includes("provider endpoint")
    || lower.includes("api key")
    || lower.includes("connection")
    || lower.includes("timeout")
  ) {
    return context.t("chatErrorModelUnavailable");
  }
  if (lower.includes("vault") || lower.includes("knowledge base")) {
    return context.t("chatErrorVaultUnavailable");
  }
  return context.t("chatErrorService");
}
