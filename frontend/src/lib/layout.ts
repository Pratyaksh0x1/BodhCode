import dagre from "dagre";
import type { Node } from "@xyflow/react";
import type { VisibleEdge, VisibleNode } from "./graphView";
import { layoutMemoKey } from "./graphView";

export const FOLDER_NODE_WIDTH = 200;
export const FOLDER_NODE_HEIGHT = 52;
export const FILE_NODE_WIDTH = 240;
export const FILE_NODE_HEIGHT = 56;

export interface LayoutOptions {
  direction?: "LR" | "TB";
  nodeSep?: number;
  rankSep?: number;
}

// In-memory cache of computed node positions keyed by layoutMemoKey
const positionCache = new Map<string, Map<string, { x: number; y: number }>>();

/**
 * Layout visible nodes and edges using Dagre with caching.
 * Memoized on the sorted list of visible node IDs + edge IDs.
 */
export function layoutWithDagre(
  nodes: VisibleNode[],
  edges: VisibleEdge[],
  options: LayoutOptions = {}
): Node[] {
  if (nodes.length === 0) {
    return [];
  }

  const key = layoutMemoKey(nodes, edges);
  let positions = positionCache.get(key);

  if (!positions) {
    const g = new dagre.graphlib.Graph();
    g.setGraph({
      rankdir: options.direction || "LR",
      nodesep: options.nodeSep || 40,
      ranksep: options.rankSep || 80,
    });
    g.setDefaultEdgeLabel(() => ({}));

    for (const node of nodes) {
      const isFolder = node.type === "folder";
      const width = isFolder ? FOLDER_NODE_WIDTH : FILE_NODE_WIDTH;
      const height = isFolder ? FOLDER_NODE_HEIGHT : FILE_NODE_HEIGHT;
      g.setNode(node.id, { width, height });
    }

    for (const edge of edges) {
      g.setEdge(edge.source, edge.target);
    }

    dagre.layout(g);

    positions = new Map<string, { x: number; y: number }>();
    for (const node of nodes) {
      const isFolder = node.type === "folder";
      const width = isFolder ? FOLDER_NODE_WIDTH : FILE_NODE_WIDTH;
      const height = isFolder ? FOLDER_NODE_HEIGHT : FILE_NODE_HEIGHT;
      const nodePos = g.node(node.id);

      // Convert Dagre center coordinates to React Flow top-left coordinates
      const x = nodePos ? nodePos.x - width / 2 : 0;
      const y = nodePos ? nodePos.y - height / 2 : 0;
      positions.set(node.id, { x, y });
    }

    positionCache.set(key, positions);
  }

  return nodes.map((node) => {
    const pos = positions?.get(node.id) || { x: 0, y: 0 };
    return {
      id: node.id,
      type: node.type,
      position: pos,
      data: {
        id: node.id,
        name: node.name,
        folder: node.folder,
        ...node.data,
      },
    };
  });
}
