import type { GraphEdge, GraphNode, GraphView } from "../../api/client";
import { nodeViewOf } from "./GraphModel";

export function GraphNodeDetail({
  node,
  edges,
  graphView,
  t,
  onOpenPage,
}: {
  node: GraphNode | null;
  edges: GraphEdge[];
  graphView: GraphView;
  t: (key: string) => string;
  onOpenPage?: (path: string) => void;
}) {
  if (!node) {
    return <div className="node-detail">{t("selectNode")}</div>;
  }
  const relatedPages = node.pages || [];
  const openPath = graphView === "entity" ? relatedPages[0] : node.id;
  return (
    <div className="node-detail">
      <h3>{node.title}</h3>
      <div className="result-meta">
        {node.id} · {labelForGraphView(nodeViewOf(node), t)}
      </div>
      <p>{node.summary || t("noSummary")}</p>
      <div className="tag-list">
        {node.entities.length ? node.entities.map((entity) => <span key={entity}>{entity}</span>) : <em>{t("noEntities")}</em>}
      </div>
      {graphView === "entity" && (
        <>
          <div className="mini-section">
            <h4>{t("relatedWikiPages")}</h4>
            {relatedPages.length ? (
              <div className="inline-list">
                {relatedPages.slice(0, 8).map((page) => (
                  <button key={page} type="button" onClick={() => onOpenPage?.(page)}>
                    {page}
                  </button>
                ))}
              </div>
            ) : (
              <p>{t("none")}</p>
            )}
          </div>
          <div className="mini-section">
            <h4>{t("relations")}</h4>
            {edges.length ? (
              <ul className="relation-list">
                {edges.slice(0, 8).map((edge, index) => (
                  <li key={`${edge.source}-${edge.target}-${index}`}>
                    <span>{edge.source}</span>
                    <strong>{edge.label || edge.kind}</strong>
                    <span>{edge.target}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p>{t("none")}</p>
            )}
          </div>
        </>
      )}
      {graphView === "page" && (
        <dl className="mini-detail">
          <div>
            <dt>{t("pageRole")}</dt>
            <dd>{node.role === "source_digest" ? t("sourceAudit") : t("wikiPages")}</dd>
          </div>
          <div>
            <dt>{t("source")}</dt>
            <dd>{node.source || t("none")}</dd>
          </div>
        </dl>
      )}
      {onOpenPage && openPath && (
        <button className="button secondary full-width-button" type="button" onClick={() => onOpenPage(openPath)}>
          {t("openInWiki")}
        </button>
      )}
    </div>
  );
}

function labelForGraphView(value: string, t: (key: string) => string) {
  if (value === "entity") return t("entity");
  if (value === "source_audit") return t("sourceAudit");
  if (value === "wiki_page") return t("wikiPages");
  return value.replace(/_/g, " ");
}
