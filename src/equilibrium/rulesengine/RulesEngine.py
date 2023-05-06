from __future__ import annotations

from contextlib import contextmanager
from typing import Any, ClassVar, Iterator, TypeVar, cast

from equilibrium.rulesengine.Cache import Cache
from equilibrium.rulesengine.Executor import Executor
from equilibrium.rulesengine.Params import Params
from equilibrium.rulesengine.Rule import Rule
from equilibrium.rulesengine.RulesGraph import RulesGraph

T = TypeVar("T")


class RulesEngine:
    """
    A simple rules engine.
    """

    def __init__(self, rules: list[Rule] | RulesGraph, subjects: list[Any], executor: Executor | None = None) -> None:
        self.graph = RulesGraph(rules)
        self.subjects = Params(*subjects)
        self.executor = executor or Executor.simple(Cache.memory())

    _current_engine_stack: ClassVar[list[RulesEngine]] = []

    @contextmanager
    def as_current(self) -> Iterator[None]:
        """
        Set the engine as the current engine for the duration of the context. Calls to #current() will return it
        as long as the context manager is active.
        """

        try:
            RulesEngine._current_engine_stack.append(self)
            yield
        finally:
            assert RulesEngine._current_engine_stack.pop() is self

    @staticmethod
    def current() -> "RulesEngine":
        if RulesEngine._current_engine_stack:
            return RulesEngine._current_engine_stack[-1]
        raise RuntimeError("No current RulesEngine")

    def get(self, output_type: type[T], params: Params) -> T:
        global_params = params

        # Obtain the reduced graph that contains only the rules that we need.
        graph = self.graph.reduce(params.types(), output_type)

        def _recurse(params: Params, output_type: type[Any]) -> Any:
            rules = graph.rules(output_type)
            for rule in rules:
                rule_params = self.subjects.filter(rule.input_types) | params.filter(rule.input_types)
                rule_params = rule_params | Params(
                    *(self.get(t, global_params) for t in (rule.input_types - rule_params.types()))
                )
                return self.executor.execute(rule, rule_params, self)
            raise RuntimeError(f"No applicable rule found for {output_type}")

        return cast(T, _recurse(params, output_type))


def get(output_type: type[T], *inputs: object) -> T:
    """
    Delegate to the engine to retrieve the specified output type given the input parameters.
    """

    engine = RulesEngine.current()
    return engine.get(output_type, Params(*inputs))
