import cytoscape, { type Core, type ElementDefinition, type NodeCollection, type NodeSingular } from "cytoscape";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { getGraph, type GraphEdge, type GraphNode, type GraphResponse, type GraphView } from "../api/client";
import { MetricCard } from "../components/MetricCard";
import type { AppContext } from "../App";

type Props = {
  graph: GraphResponse | null;
  context?: AppContext;
  embedded?: boolean;
};

const nodeColors: Record<string, string> = {
  wiki_page: "#dcfce7",
  source_audit: "#eef2f7",
  entity: "#ccfbf1",
};

export function GraphPage({ graph, context, embedded = false }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [nodeSearch, setNodeSearch] = useState("");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [graphView, setGraphView] = useState<GraphView>("entity");
  const t = context?.t ?? ((key: string) => key);
  const focusedPageId = context?.focusedPageId || null;
  const pageGraphQuery = useQuery({
    queryKey: ["graph-page-view", context?.activeVaultId || "default"],
    queryFn: () => getGraph(context?.vaultPath || "", "page"),
    enabled: graphView === "page" && Boolean(context?.vaultPath),
    staleTime: 60_000,
  });
  const activeGraph = graphView === "page" ? pageGraphQuery.data || null : graph;

  useEffect(() => {
    if (!focusedPageId) return;
    setNodeSearch("");
  }, [focusedPageId]);

  useEffect(() => {
    setSelectedNode(null);
    setNodeSearch("");
  }, [graphView]);

  const visibleGraph = useMemo(() => {
    if (!activeGraph) return { nodes: [], edges: [] };
    const normalizedSearch = nodeSearch.trim().toLowerCase();
    const nodes = activeGraph.nodes.filter((node) => {
      if (!normalizedSearch) return true;
      return `${node.title} ${node.id} ${node.summary} ${node.entities.join(" ")}`.toLowerCase().includes(normalizedSearch);
    });
    const visibleIds = new Set(nodes.map((node) => node.id));
    const edges = activeGraph.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
    return { nodes, edges };
  }, [activeGraph, nodeSearch]);

  const nodeById = useMemo(() => new Map((activeGraph?.nodes || []).map((node) => [node.id, node])), [activeGraph]);
  const edgeByNodeId = useMemo(() => {
    const map = new Map<string, GraphEdge[]>();
    for (const edge of activeGraph?.edges || []) {
      map.set(edge.source, [...(map.get(edge.source) || []), edge]);
      map.set(edge.target, [...(map.get(edge.target) || []), edge]);
    }
    return map;
  }, [activeGraph]);
  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of activeGraph?.nodes || []) {
      const type = nodeViewOf(node);
      counts.set(type, (counts.get(type) || 0) + 1);
    }
    return counts;
  }, [activeGraph]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    cyRef.current?.destroy();
    if (!visibleGraph.nodes.length) {
      cyRef.current = null;
      setSelectedNode(null);
      return;
    }

    const degree = buildDegreeMap(visibleGraph.edges);
    const elements: ElementDefinition[] = [
      ...visibleGraph.nodes.map((node) => ({
        data: {
          id: node.id,
          label: node.title,
          type: nodeViewOf(node),
          view: nodeViewOf(node),
          degree: degree.get(node.id) || 0,
        },
      })),
      ...visibleGraph.edges.map((edge, index) => ({
        data: {
          id: `${edge.source}->${edge.target}:${index}`,
          source: edge.source,
          target: edge.target,
          label: edge.label || "",
        },
      })),
    ];

    const cy = cytoscape({
      container,
      elements,
      minZoom: 0.25,
      maxZoom: 2.5,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele) => nodeColors[String(ele.data("view"))] || "#ffffff",
            "border-color": "#172033",
            "border-width": 1.2,
            color: "#40516a",
            "font-size": 10,
            height: (ele: NodeSingular) => Math.min(20, 8 + Number(ele.data("degree") || 0) * 0.9),
            label: "data(label)",
            "text-max-width": "96px",
            "text-valign": "bottom",
            "text-wrap": "ellipsis",
            "text-margin-y": 6,
            width: (ele: NodeSingular) => Math.min(20, 8 + Number(ele.data("degree") || 0) * 0.9),
          },
        },
        {
          selector: "edge",
          style: {
            "curve-style": "bezier",
            opacity: 0.58,
            "line-color": "#b8c4d4",
            width: 1.1,
          },
        },
        {
          selector: "edge[label]",
          style: {
            color: "#5b6b63",
            "font-size": 8,
            label: "data(label)",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.86,
            "text-background-padding": "2px",
            "text-rotation": "autorotate",
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-color": "#0f766e",
            "border-width": 3,
          },
        },
        {
          selector: ".neighbor",
          style: {
            "border-color": "#0f766e",
            "border-width": 2,
          },
        },
        {
          selector: ".type-muted",
          style: {
            opacity: 0.35,
          },
        },
        {
          selector: ".faded",
          style: {
            opacity: 0.18,
          },
        },
      ],
    });

    const layout = cy.layout(buildLayout());
    layout.one("layoutstop", () => {
      arrangeDisconnectedComponents(cy);
      applyViewport(cy);
    });
    layout.run();

    const selectNode = (node: NodeSingular) => {
      const page = nodeById.get(String(node.id()));
      setSelectedNode(page || null);
      cy.elements().removeClass("faded neighbor");
      node.select();
      const neighborhood = node.closedNeighborhood();
      cy.elements().not(neighborhood).addClass("faded");
      neighborhood.nodes().addClass("neighbor");
    };

    cy.on("tap", "node", (event) => selectNode(event.target));
    cy.on("tap", (event) => {
      if (event.target === cy) {
        cy.elements().removeClass("faded neighbor");
      }
    });

    cyRef.current = cy;
    const focusedNode = focusedPageId ? cy.$id(focusedPageId) : cy.collection();
    if (focusedNode.nonempty()) {
      selectNode(focusedNode[0]);
      cy.center(focusedNode);
    } else {
      setSelectedNode(visibleGraph.nodes[0] || null);
    }
    return () => cy.destroy();
  }, [focusedPageId, nodeById, visibleGraph]);

  if (!activeGraph && graphView === "entity") {
    return (
      <section className="view active">
        <article className="panel">{t("graphLoading")}</article>
      </section>
    );
  }
  if (!activeGraph && graphView === "page") {
    return (
      <section className={embedded ? "embedded-section" : "view active"}>
        <article className="panel">{t("graphLoading")}</article>
      </section>
    );
  }

  const graphData = activeGraph as GraphResponse;

  return (
    <section className={embedded ? "embedded-section" : "view active"}>
      <div className="metric-grid">
        <MetricCard label={graphView === "entity" ? t("entityNodes") : t("graphNodes")} value={graphData.stats.page_count} hint={graphView === "entity" ? t("entityNodesHint") : t("maintainedPages")} />
        <MetricCard label={graphView === "entity" ? t("relationEdges") : t("graphEdges")} value={graphData.stats.edge_count} hint={graphView === "entity" ? t("relationEdgesHint") : t("resolvedWikilinks")} />
        <MetricCard label={t("orphans")} value={graphData.stats.orphan_count} hint={graphView === "entity" ? t("entityOrphanHint") : t("orphanHint")} />
        <MetricCard label={t("unresolvedLinks")} value={graphData.stats.unresolved_link_count} hint={t("unresolvedHint")} />
      </div>

      <div className="panel-grid graph-workspace">
        <article className="panel graph-panel">
          <div className="panel-header">
            <div>
              <h2>{graphView === "entity" ? t("entityRelationGraph") : t("pageLinkGraph")}</h2>
              <p className="panel-copy">{graphView === "entity" ? t("entityGraphSubtitle") : t("pageGraphSubtitle")}</p>
            </div>
            <div className="graph-actions">
              <div className="segmented-control compact" role="tablist" aria-label={t("graphMode")}>
                <button className={graphView === "entity" ? "active" : ""} type="button" onClick={() => setGraphView("entity")}>
                  {t("entityGraphMode")}
                </button>
                <button className={graphView === "page" ? "active" : ""} type="button" onClick={() => setGraphView("page")}>
                  {t("pageGraphMode")}
                </button>
              </div>
              <label className="field graph-search">
                <span>{t("graphSearch")}</span>
                <input value={nodeSearch} onChange={(event) => setNodeSearch(event.target.value)} placeholder={t("graphSearchPlaceholder")} />
              </label>
              <button className="button secondary" onClick={() => cyRef.current?.fit(undefined, 42)}>
                {t("fit")}
              </button>
            </div>
          </div>
          <div className="graph-legend" aria-label={t("graphLegend")}>
            {graphView === "entity" ? (
              <span>
                <i style={{ background: nodeColors.entity }} />
                {t("entityNodes")} · {typeCounts.get("entity") || 0}
              </span>
            ) : (
              <span>
                <i style={{ background: nodeColors.wiki_page }} />
                {t("wikiPages")} · {typeCounts.get("wiki_page") || 0}
              </span>
            )}
          </div>
          <div className="graph-canvas" ref={containerRef}>
            {!visibleGraph.nodes.length && <div className="graph-empty">{t("noPagesToDisplay")}</div>}
          </div>
        </article>

        <aside className="panel graph-side">
          <div className="panel-header">
            <h2>{graphView === "entity" ? t("selectedEntity") : t("selectedPage")}</h2>
          </div>
          <NodeDetail node={selectedNode} edges={selectedNode ? edgeByNodeId.get(selectedNode.id) || [] : []} graphView={graphView} t={t} onOpenPage={context?.openWikiPage} />
        </aside>
      </div>
    </section>
  );
}

function NodeDetail({ node, edges, graphView, t, onOpenPage }: { node: GraphNode | null; edges: GraphEdge[]; graphView: GraphView; t: (key: string) => string; onOpenPage?: (path: string) => void }) {
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


function nodeViewOf(node: GraphNode) {
  if (node.type === "entity" || node.role === "entity") return "entity";
  return node.role === "source_digest" || node.id.startsWith("sources/") ? "source_audit" : "wiki_page";
}

function labelForGraphView(value: string, t: (key: string) => string) {
  if (value === "entity") return t("entity");
  if (value === "source_audit") return t("sourceAudit");
  if (value === "wiki_page") return t("wikiPages");
  return value.replace(/_/g, " ");
}

function buildLayout() {
  return {
    name: "cose",
    animate: false,
    nodeRepulsion: 26000,
    idealEdgeLength: 82,
    edgeElasticity: 60,
    gravity: 0.12,
    numIter: 1400,
    componentSpacing: 85,
    nodeOverlap: 18,
    fit: false,
    padding: 64,
  };
}

function applyViewport(cy: Core) {
  cy.fit(undefined, 96);
  const zoomFactor = 1.35;
  const nextZoom = Math.min(cy.maxZoom(), Math.max(cy.minZoom(), cy.zoom() * zoomFactor));
  cy.zoom({
    level: nextZoom,
    renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
  });
}

function arrangeDisconnectedComponents(cy: Core) {
  const components = collectComponents(cy);
  if (components.length <= 1) return;

  const sorted = components.sort((left, right) => right.length - left.length);
  const main = sorted[0];
  const satellites = sorted.slice(1);
  const mainBox = main.boundingBox();
  const center = {
    x: mainBox.x1 + mainBox.w / 2,
    y: mainBox.y1 + mainBox.h / 2,
  };
  const spacing = 130;
  const radiusX = Math.max(mainBox.w / 2 + spacing, 180);
  const radiusY = Math.max(mainBox.h / 2 + spacing, 140);

  satellites.forEach((component, index) => {
    const angle = (Math.PI * 2 * index) / satellites.length;
    const target = {
      x: center.x + Math.cos(angle) * radiusX,
      y: center.y + Math.sin(angle) * radiusY,
    };
    const box = component.boundingBox();
    const current = {
      x: box.x1 + box.w / 2,
      y: box.y1 + box.h / 2,
    };
    component.positions((node) => ({
      x: node.position("x") + target.x - current.x,
      y: node.position("y") + target.y - current.y,
    }));
  });
}

function collectComponents(cy: Core): NodeCollection[] {
  const visited = new Set<string>();
  const components: NodeCollection[] = [];
  cy.nodes().forEach((start) => {
    const startId = String(start.id());
    if (visited.has(startId)) return;
    const stack = [start];
    const members: NodeSingular[] = [];
    visited.add(startId);
    while (stack.length) {
      const node = stack.pop();
      if (!node) continue;
      members.push(node);
      node.connectedEdges().connectedNodes().forEach((neighbor) => {
        const neighborId = String(neighbor.id());
        if (!visited.has(neighborId)) {
          visited.add(neighborId);
          stack.push(neighbor);
        }
      });
    }
    let component = cy.collection();
    for (const member of members) {
      component = component.union(member);
    }
    components.push(component.nodes());
  });
  return components;
}

function buildDegreeMap(edges: Array<{ source: string; target: string }>) {
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
  }
  return degree;
}
