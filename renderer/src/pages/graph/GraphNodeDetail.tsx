import { useEffect, useState } from "react";

import { getPage, type GraphNode, type PageDetail } from "../../api/client";
import type { GraphAppContext } from "../../appContext";
import { AsyncMarkdownPreview } from "../../components/AsyncMarkdownPreview";
import { LoadingBlock } from "../../components/LoadingBlock";
import { userFacingError } from "../../userFacingError";

export function GraphNodeDetail({ active, node, context }: { active: boolean; node: GraphNode | null; context: GraphAppContext }) {
  const [page, setPage] = useState<PageDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    setPage(null);
    setError(null);
    if (!node) return;
    let cancelled = false;
    setLoading(true);
    getPage(context.activeVaultSelector, node.id)
      .then((detail) => {
        if (!cancelled) setPage(detail);
      })
      .catch((reason) => {
        if (!cancelled) setError(userFacingError(reason, context.language));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active, context.activeVaultSelector, context.language, node]);

  if (!node) return <div className="node-detail">{context.t("selectNode")}</div>;

  return (
    <div className="node-detail graph-raw-detail">
      <div className="graph-raw-detail-header">
        <h3>{page?.summary.title || node.title}</h3>
        <button className="button secondary small-button" type="button" onClick={() => context.openWikiPage(node.id)}>
          {context.t("openInWiki")}
        </button>
      </div>
      {loading && <LoadingBlock title={context.t("wikiPageLoading")} copy={context.t("wikiPageLoadingCopy")} compact />}
      {!loading && error && <p className="graph-raw-unavailable">{error}</p>}
      {!loading && page && (
        <AsyncMarkdownPreview
          className="graph-raw-preview"
          content={page.raw_content || page.content}
          vaultPath={context.vaultPath}
        />
      )}
    </div>
  );
}
