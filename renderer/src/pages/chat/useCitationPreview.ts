import { useState } from "react";

import { getPage, type ChatCitation } from "../../api/client";
import type { AppContext } from "../../appContext";
import { citationSelector, openCitationTarget } from "./ChatEvidence";
import type { ChatCitationPreview } from "./ChatModel";

export function useCitationPreview(context: AppContext) {
  const [citationPreview, setCitationPreview] = useState<ChatCitationPreview | null>(null);

  async function openCitationPreview(citation: ChatCitation) {
    if (citation.kind !== "page" || !citation.path) {
      openCitationTarget(citation, context);
      return;
    }
    setCitationPreview({ citation, page: null, loading: true, error: null });
    try {
      const page = await getPage(citationSelector(citation, context), citation.path);
      setCitationPreview({ citation, page, loading: false, error: null });
    } catch (error) {
      setCitationPreview({
        citation,
        page: null,
        loading: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return { citationPreview, openCitationPreview, setCitationPreview };
}
