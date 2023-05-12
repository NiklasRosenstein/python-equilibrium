"""
Provides a generic rules engine.
"""

from equilibrium.rules.Cache import Cache
from equilibrium.rules.errors import MultipleMatchingRulesError, NoMatchingRulesError, RuleResolveError
from equilibrium.rules.Executor import Executor
from equilibrium.rules.Params import Params
from equilibrium.rules.Rule import Rule, collect_rules, rule
from equilibrium.rules.RulesEngine import RulesEngine, get
from equilibrium.rules.RulesGraph import RulesGraph

__all__ = [
    "Cache",
    "collect_rules",
    "Executor",
    "get",
    "MultipleMatchingRulesError",
    "NoMatchingRulesError",
    "Params",
    "rule",
    "Rule",
    "RuleResolveError",
    "RulesEngine",
    "RulesGraph",
]
