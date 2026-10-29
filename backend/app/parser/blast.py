"""Pure graph algorithms and blast radius calculations over dependency graphs."""

from collections import deque
from typing import TYPE_CHECKING, Any

import networkx as nx

if TYPE_CHECKING:
    from app.parser.graph import GraphDoc


class NodeNotFound(Exception):
    """Raised when a requested file node does not exist in the dependency graph."""


class Impact(dict):
    """Impact representation for a single affected file in a blast radius / dependency query."""

    def __init__(self, file: str, depth: int, via: str) -> None:
        super().__init__(file=file, depth=depth, via=via)

    @property
    def file(self) -> str:
        return self["file"]

    @property
    def depth(self) -> int:
        return self["depth"]

    @property
    def via(self) -> str:
        return self["via"]


def to_digraph(doc: "GraphDoc", include_type_only: bool = True) -> nx.DiGraph:
    """Build a networkx.DiGraph from a GraphDoc.

    Edge direction is: source imports target.
    If include_type_only is False, purely type-only edges are omitted.
    """
    g = nx.DiGraph()

    for node in doc.nodes:
        g.add_node(
            node.id,
            name=node.name,
            folder=node.folder,
            size=node.size,
            exports=node.exports,
            has_default_export=node.has_default_export,
            external_deps=node.external_deps,
            unresolved_count=node.unresolved_count,
            unresolved_dynamic=node.unresolved_dynamic,
            flags=node.flags,
        )

    for edge in doc.edges:
        if not include_type_only and edge.type_only:
            continue

        if g.has_edge(edge.source, edge.target):
            existing = g[edge.source][edge.target]
            existing["count"] += edge.count
            if not edge.type_only:
                existing["type_only"] = False
            existing["kinds"].add(edge.kind)
        else:
            g.add_edge(
                edge.source,
                edge.target,
                kind=edge.kind,
                kinds={edge.kind},
                type_only=edge.type_only,
                count=edge.count,
            )

    return g


def walk(
    g: nx.DiGraph,
    file: str,
    direction: str = "upstream",
    depth: int | None = 2,
    *,
    include_type_only: bool = True,
) -> list[Impact]:
    """Single BFS walk over dependency graph in specified direction.

    - direction in ('upstream', 'importers', 'reverse', 'blast_radius'):
      Traverses backwards (predecessors) to find files importing `file`.
    - direction in ('downstream', 'dependencies', 'forward', 'imports'):
      Traverses forwards (successors) to find files imported by `file`.
    - depth: maximum traversal depth. If None, traversal is unlimited. Default is 2.

    Raises NodeNotFound if file is not in g.
    Returns list of Impact sorted by (depth, file). Target file itself is not included.
    """
    if file not in g:
        raise NodeNotFound(f"Node '{file}' not found in graph")

    if depth is not None and depth <= 0:
        return []

    is_upstream = direction.lower() in ("upstream", "importers", "reverse", "blast_radius")

    visited: set[str] = {file}
    queue: deque[tuple[str, int]] = deque([(file, 0)])
    impacts: list[Impact] = []

    while queue:
        curr, curr_depth = queue.popleft()
        if depth is not None and curr_depth >= depth:
            continue

        neighbors: list[str] = []
        if is_upstream:
            for pred in g.predecessors(curr):
                edge_data: dict[str, Any] = g[pred][curr]
                if not include_type_only and edge_data.get("type_only", False):
                    continue
                neighbors.append(pred)
        else:
            for succ in g.successors(curr):
                edge_data = g[curr][succ]
                if not include_type_only and edge_data.get("type_only", False):
                    continue
                neighbors.append(succ)

        neighbors.sort()

        for neighbor in neighbors:
            if neighbor not in visited:
                visited.add(neighbor)
                next_depth = curr_depth + 1
                impacts.append(Impact(file=neighbor, depth=next_depth, via=curr))
                queue.append((neighbor, next_depth))

    impacts.sort(key=lambda x: (x["depth"], x["file"]))
    return impacts


def blast_radius(
    g: nx.DiGraph,
    file: str,
    *,
    include_type_only: bool = True,
    max_depth: int | None = None,
) -> list[Impact]:
    """Calculate all files transitively importing the target file.

    Thin wrapper around walk(g, file, direction='upstream', depth=max_depth).
    """
    return walk(
        g,
        file,
        direction="upstream",
        depth=max_depth,
        include_type_only=include_type_only,
    )


def dependencies(
    g: nx.DiGraph,
    file: str,
    *,
    depth: int | None = 2,
    include_type_only: bool = True,
) -> list[Impact]:
    """Calculate files imported by target file up to given depth (forward BFS).

    Thin wrapper around walk(g, file, direction='downstream', depth=depth).
    """
    return walk(
        g,
        file,
        direction="downstream",
        depth=depth,
        include_type_only=include_type_only,
    )


def dependents(g: nx.DiGraph, file: str) -> list[str]:
    """Return direct importers of target file, sorted alphabetically.

    Raises NodeNotFound if file is not in g.
    """
    if file not in g:
        raise NodeNotFound(f"Node '{file}' not found in graph")

    return sorted(g.predecessors(file))


def find_cycles(g: nx.DiGraph) -> list[list[str]]:
    """Find cycles: strongly connected components with >1 node plus single-node self-loops.

    Each cycle is internally sorted; returned list is sorted by first element.
    """
    cycles: list[list[str]] = []

    for scc in nx.strongly_connected_components(g):
        if len(scc) > 1:
            cycles.append(sorted(scc))
        elif len(scc) == 1:
            node = next(iter(scc))
            if g.has_edge(node, node):
                cycles.append([node])

    cycles.sort(key=lambda c: c[0] if c else "")
    return cycles


def degree_stats(g: nx.DiGraph) -> dict[str, dict[str, int]]:
    """Return degree statistics (fan_in and fan_out) for each node in graph."""
    return {
        node: {
            "fan_in": g.in_degree(node),
            "fan_out": g.out_degree(node),
        }
        for node in sorted(g.nodes())
    }
