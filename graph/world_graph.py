from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, Dict, List, Set, Tuple


class WorldDependencyGraph:
    """World dependency graph for OmniNexus.

    This graph is intended to model global dependencies between markets,
    assets, and macro signals for downstream reasoning.
    """

    def __init__(self) -> None:
        self.graph: DefaultDict[str, Set[str]] = defaultdict(set)

    def add_dependency(self, source: str, target: str) -> None:
        self.graph[source].add(target)

    def add_bidirectional_dependency(self, a: str, b: str) -> None:
        self.add_dependency(a, b)
        self.add_dependency(b, a)

    def get_neighbors(self, node: str) -> List[str]:
        return sorted(self.graph.get(node, []))

    def build_from_edges(self, edges: List[Tuple[str, str]]) -> None:
        for source, target in edges:
            self.add_dependency(source, target)

    def to_dict(self) -> Dict[str, List[str]]:
        return {node: sorted(neighbors) for node, neighbors in self.graph.items()}


def example_graph() -> WorldDependencyGraph:
    graph = WorldDependencyGraph()
    graph.add_dependency("gold", "usd")
    graph.add_dependency("gbp", "eur")
    return graph
