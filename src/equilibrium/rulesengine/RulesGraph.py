from __future__ import annotations

from itertools import pairwise
from typing import Any, Collection, Iterable

from networkx import MultiDiGraph
from networkx.algorithms.dag import is_directed_acyclic_graph
from networkx.algorithms.shortest_paths.generic import shortest_path

from equilibrium.rulesengine.Rule import Rule


class RulesGraph:
    """
    This graph contains types as the nodes and rules are the edges.
    """

    def __init__(self, rules: Collection[Rule] | RulesGraph) -> None:
        if isinstance(rules, RulesGraph):
            self._rules: dict[str, Rule] = rules._rules.copy()
        else:
            self._rules = {r.id: r for r in rules}

        self._graph = MultiDiGraph()
        for rule in self._rules.values():
            self._graph.add_nodes_from(rule.input_types)
            self._graph.add_node(rule.output_type)
            for input_type in rule.input_types:
                self._graph.add_edge(input_type, rule.output_type, rule=rule)

        if not is_directed_acyclic_graph(self._graph):  # type: ignore[no-untyped-call]
            raise ValueError("Rules graph is not acyclic")

    def __iter__(self) -> Iterable[Rule]:
        return iter(self._rules.values())

    def __len__(self) -> int:
        return len(self._rules)

    def __getitem__(self, rule_id: str) -> Rule:
        return self._rules[rule_id]

    def rules(self, output_type: type[Any]) -> set[Rule]:
        """
        Return all rules that can generate the specified output type.
        """

        rules: set[Rule] = set()
        for edge in self._graph.in_edges(output_type):
            for data in self._graph.get_edge_data(*edge).values():
                rules.add(data["rule"])
        return rules

    def reduce(self, input_types: Collection[type[Any]], output_type: type[Any]) -> RulesGraph:
        """
        Returns a reduced graph that contains only the nodes on the path from the *input_types* to the *output_type*.
        """

        rules = set[Rule]()
        for input_type in input_types:
            for edge in pairwise(shortest_path(self._graph, input_type, output_type)):
                rules.update(d["rule"] for d in self._graph.get_edge_data(*edge).values())
        return RulesGraph(rules)
