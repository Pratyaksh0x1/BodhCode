"""Thread-safe LRU in-memory cache for parsed dependency DiGraphs."""

import threading
from collections import OrderedDict
from typing import Final

import networkx as nx

from app.models.graph import RepoGraph
from app.parser.blast import to_digraph
from app.parser.graph import GraphDoc

MAX_CACHE_SIZE: Final[int] = 20

_GRAPH_CACHE: OrderedDict[tuple[int, str, int], nx.DiGraph] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def get_cached_digraph(repo_graph: RepoGraph) -> nx.DiGraph:
    """Retrieve cached parsed DiGraph or parse and cache from stored JSON."""
    key = (repo_graph.repo_id, repo_graph.commit_sha, repo_graph.parser_version)
    with _CACHE_LOCK:
        if key in _GRAPH_CACHE:
            _GRAPH_CACHE.move_to_end(key)
            return _GRAPH_CACHE[key]

    doc = GraphDoc.from_json(repo_graph.graph_json)
    g = to_digraph(doc, include_type_only=True)

    with _CACHE_LOCK:
        _GRAPH_CACHE[key] = g
        _GRAPH_CACHE.move_to_end(key)
        if len(_GRAPH_CACHE) > MAX_CACHE_SIZE:
            _GRAPH_CACHE.popitem(last=False)
        return g


def clear_graph_cache() -> None:
    """Clear all cached graphs from memory."""
    with _CACHE_LOCK:
        _GRAPH_CACHE.clear()
