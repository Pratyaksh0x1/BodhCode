import { describe, expect, it } from "vitest";
import {
  ancestorsOf,
  canExpandAll,
  canExpandFolder,
  initialExpanded,
  layoutMemoKey,
  MAX_VISIBLE_NODES,
  representativeOf,
  visibleEdges,
  visibleNodes,
} from "./graphView";
import type { GraphDoc } from "./repos";

function createMockGraph(): GraphDoc {
  return {
    version: 1,
    repo: {
      owner: "test-owner",
      name: "test-repo",
      commit_sha: "abcd123",
    },
    nodes: [
      {
        id: "src/index.ts",
        name: "index.ts",
        folder: "src",
        size: 100,
        exports: ["main"],
        has_default_export: false,
        external_deps: [],
        unresolved_count: 0,
        unresolved_dynamic: 0,
        flags: [],
      },
      {
        id: "src/utils/math.ts",
        name: "math.ts",
        folder: "src/utils",
        size: 80,
        exports: ["add", "sub"],
        has_default_export: false,
        external_deps: [],
        unresolved_count: 0,
        unresolved_dynamic: 0,
        flags: [],
      },
      {
        id: "src/utils/string.ts",
        name: "string.ts",
        folder: "src/utils",
        size: 90,
        exports: ["capitalize"],
        has_default_export: false,
        external_deps: [],
        unresolved_count: 0,
        unresolved_dynamic: 0,
        flags: [],
      },
      {
        id: "src/components/Button.tsx",
        name: "Button.tsx",
        folder: "src/components",
        size: 120,
        exports: ["Button"],
        has_default_export: true,
        external_deps: ["react"],
        unresolved_count: 0,
        unresolved_dynamic: 0,
        flags: [],
      },
    ],
    edges: [
      {
        id: "src/index.ts->src/utils/math.ts",
        source: "src/index.ts",
        target: "src/utils/math.ts",
        kind: "import",
        type_only: false,
        count: 2,
      },
      {
        id: "src/index.ts->src/utils/string.ts",
        source: "src/index.ts",
        target: "src/utils/string.ts",
        kind: "reexport",
        type_only: true,
        count: 1,
      },
      {
        id: "src/components/Button.tsx->src/utils/string.ts",
        source: "src/components/Button.tsx",
        target: "src/utils/string.ts",
        kind: "dynamic",
        type_only: false,
        count: 1,
      },
      {
        id: "src/utils/math.ts->src/utils/string.ts",
        source: "src/utils/math.ts",
        target: "src/utils/string.ts",
        kind: "import",
        type_only: false,
        count: 1,
      },
    ],
    folders: [
      { id: "src", parent: "", file_count: 4 },
      { id: "src/utils", parent: "src", file_count: 2 },
      { id: "src/components", parent: "src", file_count: 1 },
    ],
    stats: {
      files: 4,
      edges: 4,
      external_packages: 1,
      cycles: 0,
      unresolved: 0,
    },
  };
}

describe("graphView", () => {
  describe("ancestorsOf", () => {
    it("returns root-to-parent folder path", () => {
      expect(ancestorsOf("src/components/ui/Button.tsx")).toEqual([
        "src",
        "src/components",
        "src/components/ui",
      ]);
    });

    it("returns empty array for root file", () => {
      expect(ancestorsOf("README.md")).toEqual([]);
    });

    it("returns single ancestor for immediate subfolder file", () => {
      expect(ancestorsOf("src/index.ts")).toEqual(["src"]);
    });
  });

  describe("representativeOf", () => {
    it("returns nearest collapsed ancestor folder when root folder is collapsed", () => {
      const expanded = new Set<string>();
      expect(representativeOf("src/components/Button.tsx", expanded)).toBe("src");
      expect(representativeOf("src/utils/math.ts", expanded)).toBe("src");
    });

    it("returns immediate folder when root is expanded but child folder is collapsed", () => {
      const expanded = new Set<string>(["src"]);
      expect(representativeOf("src/components/Button.tsx", expanded)).toBe("src/components");
      expect(representativeOf("src/utils/math.ts", expanded)).toBe("src/utils");
      expect(representativeOf("src/index.ts", expanded)).toBe("src/index.ts");
    });

    it("returns file id itself when all ancestors are expanded", () => {
      const expanded = new Set<string>(["src", "src/components", "src/utils"]);
      expect(representativeOf("src/components/Button.tsx", expanded)).toBe("src/components/Button.tsx");
      expect(representativeOf("src/utils/math.ts", expanded)).toBe("src/utils/math.ts");
      expect(representativeOf("src/index.ts", expanded)).toBe("src/index.ts");
    });

    it("handles root-level files", () => {
      const expanded = new Set<string>();
      expect(representativeOf("package.json", expanded)).toBe("package.json");
    });
  });

  describe("visibleNodes", () => {
    it("aggregates nodes into collapsed folders", () => {
      const graph = createMockGraph();
      // When nothing is expanded, only "src" is visible
      const nodesCollapsed = visibleNodes(graph, new Set());
      expect(nodesCollapsed).toHaveLength(1);
      expect(nodesCollapsed[0].id).toBe("src");
      expect(nodesCollapsed[0].type).toBe("folder");
      expect(nodesCollapsed[0].data.fileCount).toBe(4);

      // When "src" is expanded, "src/components", "src/utils", and "src/index.ts" are visible
      const nodesSrcExpanded = visibleNodes(graph, new Set(["src"]));
      expect(nodesSrcExpanded.map((n) => n.id)).toEqual([
        "src/components",
        "src/index.ts",
        "src/utils",
      ]);
      expect(nodesSrcExpanded.find((n) => n.id === "src/index.ts")?.type).toBe("file");
      expect(nodesSrcExpanded.find((n) => n.id === "src/utils")?.type).toBe("folder");

      // When all are expanded, all 4 files are visible
      const nodesAllExpanded = visibleNodes(
        graph,
        new Set(["src", "src/components", "src/utils"])
      );
      expect(nodesAllExpanded).toHaveLength(4);
      expect(nodesAllExpanded.every((n) => n.type === "file")).toBe(true);
    });
  });

  describe("visibleEdges", () => {
    it("drops edges where source and target collapse to the same representative (self-loops)", () => {
      const graph = createMockGraph();
      // When nothing is expanded, all nodes map to "src" -> all edges drop to self-loops
      const edgesNone = visibleEdges(graph, new Set());
      expect(edgesNone).toEqual([]);
    });

    it("merges duplicate parallel edges, aggregates kinds and counts, drops self-edges within folders", () => {
      const graph = createMockGraph();
      // "src" expanded, but "src/utils" collapsed
      // index.ts -> math.ts (maps to index.ts -> src/utils)
      // index.ts -> string.ts (maps to index.ts -> src/utils)
      // Button.tsx is in src/components (maps to src/components -> src/utils)
      // math.ts -> string.ts (maps to src/utils -> src/utils, DROPPED)
      const edges = visibleEdges(graph, new Set(["src"]));

      expect(edges).toHaveLength(2);

      const toUtils = edges.find((e) => e.target === "src/utils" && e.source === "src/index.ts");
      expect(toUtils).toBeDefined();
      expect(toUtils?.count).toBe(3); // 2 + 1
      expect(Array.from(toUtils?.kinds || []).sort()).toEqual(["import", "reexport"]);
      // One was type_only=false, one was type_only=true -> not all are type only
      expect(toUtils?.typeOnlyOnly).toBe(false);

      const compToUtils = edges.find(
        (e) => e.source === "src/components" && e.target === "src/utils"
      );
      expect(compToUtils).toBeDefined();
      expect(compToUtils?.count).toBe(1);
      expect(Array.from(compToUtils?.kinds || [])).toEqual(["dynamic"]);
    });

    it("respects edgeKindsVisible filter", () => {
      const graph = createMockGraph();
      const allExpanded = new Set(["src", "src/components", "src/utils"]);

      const withoutDynamic = visibleEdges(graph, allExpanded, {
        edgeKindsVisible: { dynamic: false },
      });
      expect(withoutDynamic.some((e) => e.kinds.has("dynamic"))).toBe(false);
    });

    it("respects hideTypeOnly filter", () => {
      const graph = createMockGraph();
      const allExpanded = new Set(["src", "src/components", "src/utils"]);

      const withoutTypeOnly = visibleEdges(graph, allExpanded, {
        hideTypeOnly: true,
      });
      expect(
        withoutTypeOnly.some(
          (e) => e.source === "src/index.ts" && e.target === "src/utils/string.ts"
        )
      ).toBe(false);
    });
  });

  describe("initialExpanded", () => {
    it("expands single top-level folder automatically", () => {
      const graph = createMockGraph();
      const initial = initialExpanded(graph);
      expect(Array.from(initial)).toEqual(["src"]);
    });

    it("expands nothing if there are multiple top-level folders", () => {
      const graph = createMockGraph();
      graph.folders.push({ id: "packages", parent: "", file_count: 5 });
      const initial = initialExpanded(graph);
      expect(Array.from(initial)).toEqual([]);
    });
  });

  describe("node cap logic (MAX_VISIBLE_NODES = 600)", () => {
    it("canExpandFolder enforces cap", () => {
      const graph = createMockGraph();
      // Test with custom cap of 2
      const expanded = new Set<string>();
      // Expanding "src" yields 3 nodes (src/components, src/utils, src/index.ts)
      expect(canExpandFolder("src", graph, expanded, 2)).toBe(false);
      expect(canExpandFolder("src", graph, expanded, 5)).toBe(true);
    });

    it("canExpandAll enforces cap", () => {
      const graph = createMockGraph();
      // All expanded produces 4 nodes
      expect(canExpandAll(graph, 3)).toBe(false);
      expect(canExpandAll(graph, 4)).toBe(true);
      expect(canExpandAll(graph, MAX_VISIBLE_NODES)).toBe(true);
    });
  });

  describe("layoutMemoKey", () => {
    it("produces identical stable key regardless of node/edge insertion order", () => {
      const graph = createMockGraph();
      const nodes = visibleNodes(graph, new Set(["src"]));
      const edges = visibleEdges(graph, new Set(["src"]));

      const key1 = layoutMemoKey(nodes, edges);
      const key2 = layoutMemoKey([...nodes].reverse(), [...edges].reverse());

      expect(key1).toBe(key2);
      expect(key1).toContain("src/components,src/index.ts,src/utils");
    });
  });
});
