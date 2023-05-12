from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from equilibrium.rulesengine.Rule import Rule
    from equilibrium.rulesengine.RulesGraph import RulesGraph
    from equilibrium.rulesengine.Signature import Signature


class RuleResolveError(Exception):
    pass


@dataclass
class NoMatchingRulesError(RuleResolveError):
    sig: Signature
    graph: RulesGraph

    def __str__(self) -> str:
        return (
            f"No rule(s) satisfy the signature ∈ {self.sig}.\n"
            f"Available rules for output type {self.sig.output_type.__name__} are:\n"
            + "\n".join(f"  {rule.id}: {rule.signature}" for rule in self.graph.rules_for(self.sig.output_type))
        )


@dataclass
class MultipleMatchingRulesError(RuleResolveError):
    sig: Signature
    paths: list[list[Rule]]
    graph: RulesGraph

    def __str__(self) -> str:
        return (
            f"Multiple paths through the rules graph satisfy the signature ∈ {self.sig}.\n"
            "The following paths were found:\n"
            + "\n\n".join(
                f"  {idx:>2}: " + "\n      ".join(f"{rule.signature} [rule id: {rule.id}]" for rule in rules)
                for idx, rules in enumerate(sorted(self.paths, key=len))
            )
        )