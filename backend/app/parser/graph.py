"""Pure graph builder and schema serialization for repository dependencies."""

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Final

from app.parser.types import AnalyzedFile

PARSER_VERSION: Final[int] = 2
MAX_GRAPH_NODES: Final[int] = 5000
MAX_GRAPH_EDGES: Final[int] = 20000


class GraphTooLargeError(Exception):
    """Raised when dependency graph node or edge counts exceed configured limits."""


@dataclass(frozen=True)
class RepoMeta:
    """Repository identification metadata."""

    owner: str
    name: str
    commit_sha: str


@dataclass(frozen=True)
class NodeDoc:
    """Metadata for a single file node in dependency graph."""

    id: str
    name: str
    folder: str
    size: int
    exports: list[str]
    has_default_export: bool
    external_deps: list[str]
    unresolved_count: int
    unresolved_dynamic: int
    flags: list[str]
    loc: int = 0
    content_hash: str = ""
    role: str | None = None


@dataclass(frozen=True)
class EdgeDoc:
    """Directed dependency edge representing an import or re-export."""

    id: str
    source: str
    target: str
    kind: str
    type_only: bool
    count: int


@dataclass(frozen=True)
class FolderDoc:
    """Ancestor folder node with recursive file count."""

    id: str
    parent: str
    file_count: int


@dataclass(frozen=True)
class StatsDoc:
    """Summary metrics of the dependency graph."""

    files: int
    edges: int
    external_packages: int
    cycles: int
    unresolved: int


@dataclass(frozen=True)
class GraphDoc:
    """Canonical versioned dependency graph document."""

    version: int
    repo: dict[str, str]
    nodes: list[NodeDoc]
    edges: list[EdgeDoc]
    folders: list[FolderDoc]
    stats: StatsDoc
    coverage: dict[str, Any] = None  # type: ignore[assignment]
    framework: str | None = None
    routes: list[dict[str, Any]] = None  # type: ignore[assignment]
    insights: list[dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.coverage is None:
            object.__setattr__(
                self,
                "coverage",
                {"percent": None, "internal_resolved": 0, "unresolved": 0},
            )
        if self.routes is None:
            object.__setattr__(self, "routes", [])
        if self.insights is None:
            object.__setattr__(self, "insights", [])

    def to_dict(self) -> dict[str, Any]:
        """Convert GraphDoc to deterministic dictionary matching JSON schema."""
        return {
            "version": self.version,
            "repo": {
                "owner": self.repo["owner"],
                "name": self.repo["name"],
                "commit_sha": self.repo["commit_sha"],
            },
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
            "folders": [asdict(f) for f in self.folders],
            "stats": asdict(self.stats),
            "coverage": dict(self.coverage),
            "framework": self.framework,
            "routes": list(self.routes),
            "insights": list(self.insights),
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Serialize GraphDoc to deterministic JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphDoc":
        """Reconstruct GraphDoc instance from dictionary."""
        return cls(
            version=int(data["version"]),
            repo={
                "owner": str(data["repo"]["owner"]),
                "name": str(data["repo"]["name"]),
                "commit_sha": str(data["repo"]["commit_sha"]),
            },
            nodes=[
                NodeDoc(
                    id=n["id"],
                    name=n["name"],
                    folder=n["folder"],
                    size=int(n["size"]),
                    exports=list(n["exports"]),
                    has_default_export=bool(n["has_default_export"]),
                    external_deps=list(n["external_deps"]),
                    unresolved_count=int(n["unresolved_count"]),
                    unresolved_dynamic=int(n["unresolved_dynamic"]),
                    flags=list(n["flags"]),
                    loc=int(n.get("loc", 0)),
                    content_hash=str(n.get("content_hash", "")),
                    role=n.get("role"),
                )
                for n in data["nodes"]
            ],
            edges=[
                EdgeDoc(
                    id=e["id"],
                    source=e["source"],
                    target=e["target"],
                    kind=e["kind"],
                    type_only=bool(e["type_only"]),
                    count=int(e["count"]),
                )
                for e in data["edges"]
            ],
            folders=[
                FolderDoc(
                    id=f["id"],
                    parent=f["parent"],
                    file_count=int(f["file_count"]),
                )
                for f in data["folders"]
            ],
            stats=StatsDoc(
                files=int(data["stats"]["files"]),
                edges=int(data["stats"]["edges"]),
                external_packages=int(data["stats"]["external_packages"]),
                cycles=int(data["stats"]["cycles"]),
                unresolved=int(data["stats"]["unresolved"]),
            ),
            coverage=dict(
                data.get("coverage", {"percent": None, "internal_resolved": 0, "unresolved": 0})
            ),
            framework=data.get("framework"),
            routes=list(data.get("routes", [])),
            insights=list(data.get("insights", [])),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "GraphDoc":
        """Parse GraphDoc instance from JSON string."""
        return cls.from_dict(json.loads(json_str))


def build_graph(facts: list[AnalyzedFile], repo_meta: RepoMeta) -> GraphDoc:
    """Build canonical dependency graph from analyzed file facts.

    Pure function: zero network, zero database, zero LLM calls. Deterministic.
    """
    from app.parser.blast import find_cycles, to_digraph

    known_file_ids = frozenset(af.path for af in facts)

    # 1. Build nodes
    nodes: list[NodeDoc] = []
    folders_counter: dict[str, int] = defaultdict(int)

    for af in facts:
        path = af.path
        name = path.rsplit("/", 1)[-1]
        folder = path.rsplit("/", 1)[0] if "/" in path else ""

        # Recursive folder ancestry
        parts = path.split("/")[:-1]
        current_folder = ""
        for part in parts:
            current_folder = f"{current_folder}/{part}" if current_folder else part
            folders_counter[current_folder] += 1

        external_deps = sorted(
            list(
                {
                    ri.resolution.package
                    for ri in af.resolved_imports
                    if ri.resolution.kind == "external" and ri.resolution.package
                }
            )
        )
        unresolved_count = sum(
            1 for ri in af.resolved_imports if ri.resolution.kind == "unresolved"
        )

        nodes.append(
            NodeDoc(
                id=path,
                name=name,
                folder=folder,
                size=af.size,
                exports=sorted(list(af.facts.exports)),
                has_default_export=af.facts.has_default_export,
                external_deps=external_deps,
                unresolved_count=unresolved_count,
                unresolved_dynamic=af.facts.unresolved_dynamic,
                flags=sorted(list(af.facts.flags)),
                loc=af.loc or af.facts.loc,
                content_hash=af.content_hash or af.facts.content_hash,
                role=None,
            )
        )

    # Sort nodes by id
    nodes.sort(key=lambda n: n.id)

    # 2. Build edges: (source, target, kind, type_only) -> count
    edge_counts: dict[tuple[str, str, str, bool], int] = defaultdict(int)

    for af in facts:
        source = af.path
        for ri in af.resolved_imports:
            if ri.resolution.kind == "file" and ri.resolution.target:
                target = ri.resolution.target
                # Self-imports produce no edge
                if target == source:
                    continue
                # Only files in the repo become nodes/edges
                if target not in known_file_ids:
                    continue

                key = (source, target, ri.ref.kind, ri.ref.type_only)
                edge_counts[key] += 1

    edges: list[EdgeDoc] = []
    # Sort keys deterministically by (source, target, kind, type_only)
    sorted_edge_keys = sorted(
        edge_counts.keys(),
        key=lambda k: (k[0], k[1], k[2], k[3]),
    )

    for source, target, kind, type_only in sorted_edge_keys:
        count = edge_counts[(source, target, kind, type_only)]
        edge_suffix = ":type" if type_only else ""
        edge_id = f"{source}>{target}#{kind}{edge_suffix}"
        edges.append(
            EdgeDoc(
                id=edge_id,
                source=source,
                target=target,
                kind=kind,
                type_only=type_only,
                count=count,
            )
        )

    # 3. Enforce graph limits
    if len(nodes) > MAX_GRAPH_NODES or len(edges) > MAX_GRAPH_EDGES:
        raise GraphTooLargeError(
            f"Graph limits exceeded: {len(nodes)} nodes (max {MAX_GRAPH_NODES}), "
            f"{len(edges)} edges (max {MAX_GRAPH_EDGES})"
        )

    # 4. Build folders sorted by id
    folders: list[FolderDoc] = []
    for f_id in sorted(folders_counter.keys()):
        parent = f_id.rsplit("/", 1)[0] if "/" in f_id else ""
        folders.append(
            FolderDoc(
                id=f_id,
                parent=parent,
                file_count=folders_counter[f_id],
            )
        )

    # 5. Build stats and coverage (including cycles)
    all_external_packages = len({pkg for n in nodes for pkg in n.external_deps})
    total_unresolved = sum(n.unresolved_count for n in nodes)
    internal_resolved = sum(
        1 for af in facts for imp in af.resolved_imports if imp.resolution.kind == "file"
    )
    denom = internal_resolved + total_unresolved
    coverage_percent = round((internal_resolved / denom) * 100.0, 2) if denom > 0 else None
    coverage = {
        "percent": coverage_percent,
        "internal_resolved": internal_resolved,
        "unresolved": total_unresolved,
    }

    # Construct temporary doc to compute cycles via blast
    doc_for_cycles = GraphDoc(
        version=PARSER_VERSION,
        repo={
            "owner": repo_meta.owner,
            "name": repo_meta.name,
            "commit_sha": repo_meta.commit_sha,
        },
        nodes=nodes,
        edges=edges,
        folders=folders,
        stats=StatsDoc(
            files=len(nodes),
            edges=len(edges),
            external_packages=all_external_packages,
            cycles=0,
            unresolved=total_unresolved,
        ),
        coverage=coverage,
        framework=None,
        routes=[],
        insights=[],
    )

    g = to_digraph(doc_for_cycles, include_type_only=True)
    cycles_list = find_cycles(g)

    stats = StatsDoc(
        files=len(nodes),
        edges=len(edges),
        external_packages=all_external_packages,
        cycles=len(cycles_list),
        unresolved=total_unresolved,
    )

    return GraphDoc(
        version=PARSER_VERSION,
        repo={
            "owner": repo_meta.owner,
            "name": repo_meta.name,
            "commit_sha": repo_meta.commit_sha,
        },
        nodes=nodes,
        edges=edges,
        folders=folders,
        stats=stats,
        coverage=coverage,
        framework=None,
        routes=[],
        insights=[],
    )
