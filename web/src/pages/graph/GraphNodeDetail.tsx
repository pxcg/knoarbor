import type { GraphEdge, GraphNode } from "../../api/client";
export function GraphNodeDetail({
  node,
  edges,
  t,
  onOpenPage,
}: {
  node: GraphNode | null;
  edges: GraphEdge[];
  t: (key: string) => string;
  onOpenPage?: (path: string) => void;
}) {
  if (!node) {
    return <div className="node-detail">{t("selectNode")}</div>;
  }
  const openPath = node.id;
  return (
    <div className="node-detail">
      <h3>{node.title}</h3>
      <p>{node.summary || t("noSummary")}</p>
      <div className="tag-list">
        {node.entities.length ? node.entities.map((entity) => <span key={entity}>{entity}</span>) : <em>{t("noEntities")}</em>}
      </div>
      {edges.length > 0 && (
        <div className="mini-section">
          <h4>{t("relations")}</h4>
          <ul className="relation-list">
            {edges.slice(0, 8).map((edge, index) => (
              <li key={`${edge.source}-${edge.target}-${index}`}>
                <span>{edge.source}</span>
                <strong>{edge.label || edge.kind}</strong>
                <span>{edge.target}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {onOpenPage && openPath && (
        <button className="button secondary full-width-button" type="button" onClick={() => onOpenPage(openPath)}>
          {t("openInWiki")}
        </button>
      )}
    </div>
  );
}
