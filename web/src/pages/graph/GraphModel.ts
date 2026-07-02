import type { ElementDefinition } from "cytoscape";

import type { GraphEdge, GraphNode, GraphResponse } from "../../api/client";

export const nodeColors: Record<string, string> = {
  wiki_page: "#dcfce7",
};

export function filterVisibleGraph(graph: GraphResponse | null, search: string) {
  if (!graph) return { nodes: [], edges: [] };
  const normalizedSearch = search.trim().toLowerCase();
  const nodes = graph.nodes.filter((node) => {
    if (!normalizedSearch) return true;
    return `${node.title} ${node.id} ${node.summary}`.toLowerCase().includes(normalizedSearch);
  });
  const visibleIds = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
  return { nodes, edges };
}

export function mapNodesById(graph: GraphResponse | null) {
  return new Map((graph?.nodes || []).map((node) => [node.id, node]));
}

export function mapEdgesByNodeId(graph: GraphResponse | null) {
  const map = new Map<string, GraphEdge[]>();
  for (const edge of graph?.edges || []) {
    map.set(edge.source, [...(map.get(edge.source) || []), edge]);
    map.set(edge.target, [...(map.get(edge.target) || []), edge]);
  }
  return map;
}

export function graphNodeTypeCounts(graph: GraphResponse | null) {
  const counts = new Map<string, number>();
  for (const node of graph?.nodes || []) {
    const type = nodeViewOf(node);
    counts.set(type, (counts.get(type) || 0) + 1);
  }
  return counts;
}

export function buildGraphElements(nodes: GraphNode[], edges: GraphEdge[]): ElementDefinition[] {
  const degree = buildDegreeMap(edges);
  return [
    ...nodes.map((node) => ({
      data: {
        id: node.id,
        label: node.title,
        type: nodeViewOf(node),
        view: nodeViewOf(node),
        degree: degree.get(node.id) || 0,
      },
    })),
    ...edges.map((edge, index) => ({
      data: {
        id: `${edge.source}->${edge.target}:${index}`,
        source: edge.source,
        target: edge.target,
        label: edge.label || "",
      },
    })),
  ];
}

export function nodeViewOf(_node: GraphNode) {
  return "wiki_page";
}

function buildDegreeMap(edges: Array<{ source: string; target: string }>) {
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
  }
  return degree;
}
