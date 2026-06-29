import cytoscape, { type Core, type NodeCollection, type NodeSingular } from "cytoscape";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { getGraph, type GraphEdge, type GraphNode, type GraphResponse, type GraphView } from "../api/client";
import { MetricCard } from "../components/MetricCard";
import type { AppContext } from "../appContext";
import { buildGraphElements, filterVisibleGraph, graphNodeTypeCounts, mapEdgesByNodeId, mapNodesById, nodeColors } from "./graph/GraphModel";
import { GraphNodeDetail } from "./graph/GraphNodeDetail";

type Props = {
  graph: GraphResponse | null;
  context?: AppContext;
  embedded?: boolean;
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

  const visibleGraph = useMemo(() => filterVisibleGraph(activeGraph, nodeSearch), [activeGraph, nodeSearch]);
  const nodeById = useMemo(() => mapNodesById(activeGraph), [activeGraph]);
  const edgeByNodeId = useMemo(() => mapEdgesByNodeId(activeGraph), [activeGraph]);
  const typeCounts = useMemo(() => graphNodeTypeCounts(activeGraph), [activeGraph]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    cyRef.current?.destroy();
    if (!visibleGraph.nodes.length) {
      cyRef.current = null;
      setSelectedNode(null);
      return;
    }

    const elements = buildGraphElements(visibleGraph.nodes, visibleGraph.edges);

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
      <div className="graph-metrics">
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
            <div className="graph-toolbar">
              <div className="segmented-control compact" role="tablist" aria-label={t("graphMode")}>
                <button className={graphView === "entity" ? "active" : ""} type="button" onClick={() => setGraphView("entity")}>
                  {t("entityGraphMode")}
                </button>
                <button className={graphView === "page" ? "active" : ""} type="button" onClick={() => setGraphView("page")}>
                  {t("pageGraphMode")}
                </button>
              </div>
              <label className="field graph-toolbar-search">
                <span>{t("graphSearch")}</span>
                <input value={nodeSearch} onChange={(event) => setNodeSearch(event.target.value)} placeholder={t("graphSearchPlaceholder")} />
              </label>
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
          <GraphNodeDetail node={selectedNode} edges={selectedNode ? edgeByNodeId.get(selectedNode.id) || [] : []} graphView={graphView} t={t} onOpenPage={context?.openWikiPage} />
        </aside>
      </div>
    </section>
  );
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
