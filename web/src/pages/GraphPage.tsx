import cytoscape, { type Core, type ElementDefinition, type NodeCollection, type NodeSingular } from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";

import type { GraphNode, GraphResponse } from "../api/client";
import { BarChart } from "../components/BarChart";
import { MetricCard } from "../components/MetricCard";
import type { AppContext } from "../App";

type Props = {
  graph: GraphResponse | null;
  context?: AppContext;
  embedded?: boolean;
};

const nodeColors: Record<string, string> = {
  source: "#eef2f7",
  entity: "#dcfce7",
  concept: "#dbeafe",
  query: "#fef3c7",
  comparison: "#fae8ff",
  claim: "#f1f5f9",
  timeline: "#f1f5f9",
  workflow: "#f1f5f9",
};

type GraphDensity = "compact" | "balanced";

export function GraphPage({ graph, context, embedded = false }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [nodeSearch, setNodeSearch] = useState("");
  const [density, setDensity] = useState<GraphDensity>("balanced");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const t = context?.t ?? ((key: string) => key);
  const focusedPageId = context?.focusedPageId || null;

  useEffect(() => {
    if (!focusedPageId) return;
    setTypeFilter("");
    setNodeSearch("");
  }, [focusedPageId]);

  const visibleGraph = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    const normalizedSearch = nodeSearch.trim().toLowerCase();
    const nodes = graph.nodes.filter((node) => {
      if (typeFilter && nodeKindOf(node) !== typeFilter) return false;
      if (!normalizedSearch) return true;
      return `${node.title} ${node.id} ${node.summary} ${node.tags.join(" ")} ${(node.facets || []).join(" ")}`.toLowerCase().includes(normalizedSearch);
    });
    const visibleIds = new Set(nodes.map((node) => node.id));
    const edges = graph.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
    return { nodes, edges };
  }, [graph, nodeSearch, typeFilter]);

  const nodeById = useMemo(() => new Map((graph?.nodes || []).map((node) => [node.id, node])), [graph]);
  const types = useMemo(() => Array.from(new Set((graph?.nodes || []).map(nodeKindOf))).sort(), [graph]);
  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const node of graph?.nodes || []) {
      const type = nodeKindOf(node);
      counts.set(type, (counts.get(type) || 0) + 1);
    }
    return counts;
  }, [graph]);

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
          type: nodeKindOf(node),
          degree: degree.get(node.id) || 0,
        },
      })),
      ...visibleGraph.edges.map((edge, index) => ({
        data: {
          id: `${edge.source}->${edge.target}:${index}`,
          source: edge.source,
          target: edge.target,
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
            "background-color": (ele) => nodeColors[String(ele.data("type"))] || "#ffffff",
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

    const layout = cy.layout(buildLayout(density));
    layout.one("layoutstop", () => {
      arrangeDisconnectedComponents(cy, density);
      applyDensityViewport(cy, density);
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
  }, [density, focusedPageId, nodeById, typeFilter, visibleGraph]);

  if (!graph) {
    return (
      <section className="view active">
        <article className="panel">{t("graphLoading")}</article>
      </section>
    );
  }

  return (
    <section className={embedded ? "embedded-section" : "view active"}>
      <div className="metric-grid">
        <MetricCard label={t("graphNodes")} value={graph.stats.page_count} hint={t("maintainedPages")} />
        <MetricCard label={t("graphEdges")} value={graph.stats.edge_count} hint={t("resolvedWikilinks")} />
        <MetricCard label={t("orphans")} value={graph.stats.orphan_count} hint={t("orphanHint")} />
        <MetricCard label={t("unresolvedLinks")} value={graph.stats.unresolved_link_count} hint={t("unresolvedHint")} />
      </div>

      <div className="panel-grid graph-overview">
        <article className="panel chart-panel">
          <div className="panel-header compact">
            <h2>{t("pageKinds")}</h2>
          </div>
          <BarChart data={Object.keys(graph.stats.page_kind_counts || {}).length ? graph.stats.page_kind_counts : graph.stats.directory_counts} emptyText={t("noData")} />
        </article>
        <article className="panel chart-panel">
          <div className="panel-header compact">
            <h2>{t("topTags")}</h2>
          </div>
          <BarChart data={graph.stats.tag_counts} emptyText={t("noData")} />
        </article>
      </div>

      <div className="panel-grid graph-workspace">
        <article className="panel graph-panel">
          <div className="panel-header">
            <div>
              <h2>{t("pageLinkGraph")}</h2>
              <p className="panel-copy">{t("graphSubtitle")}</p>
            </div>
            <div className="graph-actions">
              <label className="field graph-search">
                <span>{t("graphSearch")}</span>
                <input value={nodeSearch} onChange={(event) => setNodeSearch(event.target.value)} placeholder={t("graphSearchPlaceholder")} />
              </label>
              <label className="field graph-filter">
                <span>{t("graphDensity")}</span>
                <select value={density} onChange={(event) => setDensity(event.target.value as GraphDensity)}>
                  <option value="compact">{t("graphDensityCompact")}</option>
                  <option value="balanced">{t("graphDensityBalanced")}</option>
                </select>
              </label>
              <label className="field graph-filter">
                <span>{t("typeFilter")}</span>
                <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
                  <option value="">{t("allPages")}</option>
                  {types.map((type) => (
                    <option value={type} key={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              <button className="button secondary" onClick={() => cyRef.current?.fit(undefined, 42)}>
                {t("fit")}
              </button>
            </div>
          </div>
          <div className="graph-legend" aria-label={t("graphLegend")}>
            {types.map((type) => (
              <span className={typeFilter === type ? "active" : ""} key={type}>
                <i style={{ background: nodeColors[type] || "#ffffff" }} />
                {type} · {typeCounts.get(type) || 0}
              </span>
            ))}
          </div>
          <div className="graph-canvas" ref={containerRef}>
            {!visibleGraph.nodes.length && <div className="graph-empty">{t("noPagesToDisplay")}</div>}
          </div>
        </article>

        <aside className="panel graph-side">
          <div className="panel-header">
            <h2>{t("selectedPage")}</h2>
          </div>
          <NodeDetail node={selectedNode} t={t} onOpenPage={context?.openWikiPage} />
        </aside>
      </div>
    </section>
  );
}

function NodeDetail({ node, t, onOpenPage }: { node: GraphNode | null; t: (key: string) => string; onOpenPage?: (path: string) => void }) {
  if (!node) {
    return <div className="node-detail">{t("selectNode")}</div>;
  }
  return (
    <div className="node-detail">
      <h3>{node.title}</h3>
      <div className="result-meta">
        {node.id} · {nodeKindOf(node)}
      </div>
      <p>{node.summary || t("noSummary")}</p>
      <div className="tag-list">
        {node.tags.length ? node.tags.map((tag) => <span key={tag}>{tag}</span>) : <em>{t("noTags")}</em>}
      </div>
      <dl className="mini-detail">
        <div>
          <dt>{t("pageRole")}</dt>
          <dd>{node.role || "knowledge_page"}</dd>
        </div>
        <div>
          <dt>{t("facets")}</dt>
          <dd>{(node.facets || []).join(", ") || t("none")}</dd>
        </div>
        <div>
          <dt>{t("source")}</dt>
          <dd>{node.source || t("none")}</dd>
        </div>
      </dl>
      {onOpenPage && (
        <button className="button secondary full-width-button" type="button" onClick={() => onOpenPage(node.id)}>
          {t("openInWiki")}
        </button>
      )}
    </div>
  );
}


function nodeKindOf(node: GraphNode) {
  return node.page_kind || node.type || "page";
}

function buildLayout(density: GraphDensity) {
  const settings = {
    compact: {
      nodeRepulsion: 65000,
      idealEdgeLength: 150,
      gravity: 0.04,
      componentSpacing: 130,
      padding: 84,
    },
    balanced: {
      nodeRepulsion: 26000,
      idealEdgeLength: 82,
      gravity: 0.12,
      componentSpacing: 85,
      padding: 64,
    },
  }[density];
  return {
    name: "cose",
    animate: false,
    nodeRepulsion: settings.nodeRepulsion,
    idealEdgeLength: settings.idealEdgeLength,
    edgeElasticity: 60,
    gravity: settings.gravity,
    numIter: 1400,
    componentSpacing: settings.componentSpacing,
    nodeOverlap: 18,
    fit: false,
    padding: settings.padding,
  };
}

function applyDensityViewport(cy: Core, density: GraphDensity) {
  const padding = {
    compact: 72,
    balanced: 96,
  }[density];
  cy.fit(undefined, padding);
  const zoomFactor = {
    compact: 1.1,
    balanced: 1.35,
  }[density];
  const nextZoom = Math.min(cy.maxZoom(), Math.max(cy.minZoom(), cy.zoom() * zoomFactor));
  cy.zoom({
    level: nextZoom,
    renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
  });
}

function arrangeDisconnectedComponents(cy: Core, density: GraphDensity) {
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
  const spacing = {
    compact: 92,
    balanced: 130,
  }[density];
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
