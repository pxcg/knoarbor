import { useCallback, useRef, useState } from "react";

import { getPage, resolveChatCitations, type ChatCitation, type QueryRawEvidence } from "../../api/client";
import type { ChatAppContext } from "../../appContext";
import { citationSelector, openCitationTarget } from "./ChatEvidence";
import type { ChatCitationPreview } from "./ChatModel";

export type CitationEvidenceSelection = {
  citation: ChatCitation;
  evidence?: QueryRawEvidence;
};

export function useCitationPreview(context: ChatAppContext) {
  const [citationPreview, setCitationPreview] = useState<ChatCitationPreview | null>(null);
  const requestGeneration = useRef(0);

  const clearCitationPreview = useCallback(() => {
    requestGeneration.current += 1;
    setCitationPreview(null);
  }, []);

  async function openCitationPreview(
    citation: ChatCitation,
    evidence?: QueryRawEvidence,
    related: CitationEvidenceSelection[] = [],
  ) {
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    const pagePath = citation.kind === "page"
      ? citation.path
      : evidence?.locator_page_paths?.[0]
        || related.find((item) => item.evidence?.locator_page_paths?.[0])?.evidence?.locator_page_paths?.[0];
    if (!pagePath) {
      setCitationPreview(null);
      try {
        await openCitationTarget(citation, context);
      } catch {
        if (generation !== requestGeneration.current) return;
        setCitationPreview({
          citation,
          page: null,
          highlightTerm: null,
          highlightTerms: [],
          loading: false,
          error: context.language === "zh" ? "该目标不存在或暂时无法读取。" : "The requested target does not exist or is temporarily unavailable.",
        });
      }
      return;
    }
    const pageHighlightTerm = citation.kind === "page" ? citation.title?.trim() || null : null;
    setCitationPreview({
      citation,
      page: null,
      highlightTerm: pageHighlightTerm,
      highlightTerms: [],
      loading: true,
      error: null,
    });
    try {
      const selector = citationSelector(citation, context);
      const citations = uniqueCitations([
        citation,
        ...related.map((item) => item.citation),
      ]);
      const [page, resolution] = await Promise.all([
        getPage(selector, pagePath),
        resolveChatCitations(selector, citations),
      ]);
      if (generation !== requestGeneration.current) return;
      const resolvedTerms = resolution.resolutions.flatMap((item) => {
        if (item.status !== "resolved") return [];
        if (item.texts?.length) return item.texts.map((text) => text.trim());
        return item.text?.trim() ? [item.text.trim()] : [];
      });
      const resolvedHighlightTerm = pageHighlightTerm || resolvedTerms[0] || null;
      const resolvedRelatedTerms = uniqueTerms(
        resolvedTerms.filter((term) => term !== resolvedHighlightTerm),
      );
      setCitationPreview({
        citation,
        page,
        highlightTerm: resolvedHighlightTerm,
        highlightTerms: resolvedRelatedTerms,
        loading: false,
        error: null,
      });
    } catch (error) {
      if (generation !== requestGeneration.current) return;
      const missing = isMissingCitationTarget(error);
      setCitationPreview({
        citation,
        page: null,
        highlightTerm: pageHighlightTerm,
        highlightTerms: [],
        loading: false,
        error: missing
          ? (context.language === "zh" ? "原始材料已删除，无法预览此引用。" : "The original material was deleted, so this citation can no longer be previewed.")
          : (context.language === "zh" ? "该来源暂时无法读取。" : "This source is temporarily unavailable."),
      });
    }
  }

  return {
    citationPreview,
    clearCitationPreview,
    openCitationPreview,
  };
}

function uniqueTerms(values: Array<string | null>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value?.trim()))));
}

function uniqueCitations(citations: ChatCitation[]) {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const key = citationIdentity(citation);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function citationIdentity(citation: ChatCitation) {
  const spans = citation.spans?.map((span) => `${span.char_start}:${span.char_end}`).join(",") || "";
  return [
    citation.kind,
    citation.vault_id || "",
    citation.vault_path || "",
    citation.path || "",
    citation.run_id || "",
    citation.evidence_id || "",
    citation.raw_revision_id || "",
    citation.source_unit_id || "",
    citation.char_start ?? "",
    citation.char_end ?? "",
    spans,
  ].join("|");
}

function isMissingCitationTarget(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  return /(?:file|page).*(?:not found|does not exist)|(?:not found|does not exist).*(?:file|page)/i.test(message);
}
