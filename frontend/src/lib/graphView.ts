/**
 * Pure dependency graph view derivation logic for the interactive canvas.
 * Zero React imports - 100% deterministic and unit-tested.
 */

import type { GraphDoc, GraphNode } from "./repos";

export const MAX_VISIBLE_NODES = 600;

export interface VisibleNode {
  id: string;
  type: "folder" | "file";
  name: string;
  folder: string;
  data: {
    node?: GraphNode;
    fileCount?: number;
    parentFolder?: string;
  };
}

export interface VisibleEdge {
  id: string;
  source: string;
  target: string;
  count: number;
  kinds: Set<string>;
  typeOnlyOnly: boolean;
  typeOnly: boolean; // alias for compatibility
}

/**
 * Return all ancestor folder IDs for a file or folder path, ordered from root down to parent.
 * e.g. "src/components/Button.tsx" -> ["src", "src/components"]
 * e.g. "index.ts" -> []
 */
export function ancestorsOf(path: string): string[] {
  const parts = path.split("/").filter(Boolean);
  // Remove the last item (filename or leaf folder)
  parts.pop();

  const ancestors: string[] = [];
  let current = "";
  for (const part of parts) {
    current = current ? `${current}/${part}` : part;
    ancestors.push(current);
  }
  return ancestors;
}

/**
 * Find the visible representative for a path.
 * Traverses from root down: returns the first collapsed ancestor folder,
 * or the path itself if every ancestor is expanded.
 */
export function representativeOf(path: string, expandedFolders: Set<string>): string {
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 1) {
    // Root level file or single folder
    return path;
  }

  // Check ancestors from root down
  let current = "";
  for (let i = 0; i < parts.length - 1; i++) {
    current = current ? `${current}/${parts[i]}` : parts[i];
    if (!expandedFolders.has(current)) {
      // First collapsed ancestor in hierarchy represents this item
      return current;
    }
  }

  // All ancestors are expanded; this file/folder represents itself
  return path;
}

/**
 * Compute the unique visible representative nodes (folders and files).
 */
export function visibleNodes(graph: GraphDoc, expandedFolders: Set<string>): VisibleNode[] {
  const repMap = new Map<string, VisibleNode>();
  const folders = graph.folders ?? [];
  const foldersById = new Map(folders.map((f) => [f.id, f]));

  for (const node of graph.nodes ?? []) {
    const repId = representativeOf(node.id, expandedFolders);
    if (repMap.has(repId)) {
      continue;
    }

    if (repId === node.id) {
      // File node (all ancestors expanded)
      repMap.set(repId, {
        id: repId,
        type: "file",
        name: node.name,
        folder: node.folder,
        data: {
          node,
        },
      });
    } else {
      // Folder node
      const folderDoc = foldersById.get(repId);
      const name = repId.includes("/") ? repId.slice(repId.lastIndexOf("/") + 1) : repId;
      const parentFolder = folderDoc?.parent || "";

      repMap.set(repId, {
        id: repId,
        type: "folder",
        name,
        folder: parentFolder,
        data: {
          fileCount: folderDoc?.file_count ?? 1,
          parentFolder,
        },
      });
    }
  }

  // Return nodes sorted by ID for determinism
  return Array.from(repMap.values()).sort((a, b) => a.id.localeCompare(b.id));
}

export interface VisibleEdgesOptions {
  edgeKindsVisible?: Record<string, boolean>;
  hideTypeOnly?: boolean;
}

/**
 * Derive visible edges between representatives.
 * - Maps source and target to representatives
 * - Drops self-loops (edges within same representative)
 * - Merges parallel edges, aggregating kinds, counts, and type-only flags
 */
export function visibleEdges(
  graph: GraphDoc,
  expandedFolders: Set<string>,
  options: VisibleEdgesOptions = {}
): VisibleEdge[] {
  const { edgeKindsVisible, hideTypeOnly = false } = options;

  interface MergedEdgeAcc {
    source: string;
    target: string;
    count: number;
    kinds: Set<string>;
    allTypeOnly: boolean;
  }

  const merged = new Map<string, MergedEdgeAcc>();

  for (const edge of graph.edges ?? []) {
    // 1. Kind filter
    if (edgeKindsVisible && edgeKindsVisible[edge.kind] === false) {
      continue;
    }

    // 2. Type-only filter
    if (hideTypeOnly && edge.type_only) {
      continue;
    }

    // 3. Map to representatives
    const sourceRep = representativeOf(edge.source, expandedFolders);
    const targetRep = representativeOf(edge.target, expandedFolders);

    // 4. Drop self-loops
    if (sourceRep === targetRep) {
      continue;
    }

    const key = `${sourceRep}->${targetRep}`;
    const existing = merged.get(key);

    if (existing) {
      existing.count += edge.count;
      existing.kinds.add(edge.kind);
      if (!edge.type_only) {
        existing.allTypeOnly = false;
      }
    } else {
      merged.set(key, {
        source: sourceRep,
        target: targetRep,
        count: edge.count,
        kinds: new Set([edge.kind]),
        allTypeOnly: edge.type_only,
      });
    }
  }

  // Convert to sorted VisibleEdge array
  return Array.from(merged.entries())
    .map(([key, val]) => ({
      id: key,
      source: val.source,
      target: val.target,
      count: val.count,
      kinds: val.kinds,
      typeOnlyOnly: val.allTypeOnly,
      typeOnly: val.allTypeOnly,
    }))
    .sort((a, b) => a.id.localeCompare(b.id));
}

/**
 * Determine initial expanded folders:
 * If the repo has exactly one top-level folder (such as "src"), expand it automatically.
 * Otherwise, expand nothing (top-level folders remain collapsed as nodes).
 */
export function initialExpanded(graph: GraphDoc): Set<string> {
  const folders = graph.folders ?? [];
  const topLevelFolders = folders.filter((f) => !f.parent || f.parent === "");
  if (topLevelFolders.length === 1) {
    return new Set([topLevelFolders[0].id]);
  }
  return new Set();
}

/**
 * Check if expanding folderId is permitted under the MAX_VISIBLE_NODES cap.
 */
export function canExpandFolder(
  folderId: string,
  graph: GraphDoc,
  expandedFolders: Set<string>,
  maxNodes: number = MAX_VISIBLE_NODES
): boolean {
  if (expandedFolders.has(folderId)) {
    return true; // Already expanded, collapsing or no-op is always permitted
  }

  const nextExpanded = new Set(expandedFolders);
  nextExpanded.add(folderId);
  const projectedCount = visibleNodes(graph, nextExpanded).length;
  return projectedCount <= maxNodes;
}

/**
 * Check if expanding all folders would exceed the node cap.
 */
export function canExpandAll(
  graph: GraphDoc,
  maxNodes: number = MAX_VISIBLE_NODES
): boolean {
  const folders = graph.folders ?? [];
  const allFolders = new Set(folders.map((f) => f.id));
  const projectedCount = visibleNodes(graph, allFolders).length;
  return projectedCount <= maxNodes;
}

/**
 * Helper to build stable layout cache key.
 */
export function layoutMemoKey(nodes: VisibleNode[], edges: VisibleEdge[]): string {
  const nodeKey = nodes.map((n) => n.id).sort().join(",");
  const edgeKey = edges.map((e) => e.id).sort().join(",");
  return `${nodeKey}|${edgeKey}`;
}
