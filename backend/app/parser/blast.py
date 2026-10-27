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


def blast_radius(
    g: nx.DiGraph,
    file: str,
    *,
    include_type_only: bool = True,
    max_depth: int | None = None,
) -> list[Impact]:
    """Calculate all files transitively importing the target file.

    Traverses reversed edges using breadth-first search (BFS).
    Returns list of Impact sorted by (depth, file). The changed file itself is not included.
    Raises NodeNotFound if file is not in g.
    """
    if file not in g:
        raise NodeNotFound(f"Node '{file}' not found in graph")

    if max_depth is not None and max_depth <= 0:
        return []

    visited: set[str] = {file}
    queue: deque[tuple[str, int]] = deque([(file, 0)])
    impacts: list[Impact] = []

    while queue:
        curr, depth = queue.popleft()
        if max_depth is not None and depth >= max_depth:
            continue

        importers: list[str] = []
        for pred in g.predecessors(curr):
            edge_data: dict[str, Any] = g[pred][curr]
            if not include_type_only and edge_data.get("type_only", False):
                continue
            importers.append(pred)

        # Sort for deterministic BFS exploration order
        importers.sort()

        for importer in importers:
            if importer not in visited:
                visited.add(importer)
                next_depth = depth + 1
                impacts.append(Impact(file=importer, depth=next_depth, via=curr))
                queue.append((importer, next_depth))

    impacts.sort(key=lambda x: (x["depth"], x["file"]))
    return impacts


def dependencies(
    g: nx.DiGraph,
    file: str,
    *,
    depth: int = 1,
    include_type_only: bool = True,
) -> list[Impact]:
    """Calculate files imported by target file up to given depth (forward BFS).

    Returns list of Impact sorted by (depth, file). Target file is not included.
    Raises NodeNotFound if file is not in g.
    """
    if file not in g:
        raise NodeNotFound(f"Node '{file}' not found in graph")

    if depth <= 0:
        return []

    visited: set[str] = {file}
    queue: deque[tuple[str, int]] = deque([(file, 0)])
    impacts: list[Impact] = []

    while queue:
        curr, d = queue.popleft()
        if d >= depth:
            continue

        imported_files: list[str] = []
        for succ in g.successors(curr):
            edge_data: dict[str, Any] = g[curr][succ]
            if not include_type_only and edge_data.get("type_only", False):
                continue
            imported_files.append(succ)

        imported_files.sort()

        for dep in imported_files:
            if dep not in visited:
                visited.add(dep)
                next_depth = d + 1
                impacts.append(Impact(file=dep, depth=next_depth, via=curr))
                queue.append((dep, next_depth))

    impacts.sort(key=lambda x: (x["depth"], x["file"]))
    return impacts


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
