from __future__ import annotations

from contextlib import contextmanager
from typing import Any, ClassVar, Iterator, Sequence, TypeVar

from equilibrium.rulesengine.Cache import Cache
from equilibrium.rulesengine.Executor import Executor
from equilibrium.rulesengine.Params import Params
from equilibrium.rulesengine.Rule import Rule
from equilibrium.rulesengine.RulesGraph import RulesGraph
from equilibrium.rulesengine.Signature import Signature

T = TypeVar("T")


class RulesEngine:
    """
    A simple rules engine.
    """

    def __init__(
        self,
        rules: list[Rule] | RulesGraph,
        subjects: Sequence[Any] | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.graph = RulesGraph(rules)
        self.subjects = Params(*subjects or ())
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
        """
        Evaluate the rules to derive the specified *output_type* from the given parameters.
        """

        sig = Signature(set(params.types()) | set(self.subjects.types()), output_type)
        rules = self.graph.find_path(sig)
        assert len(rules) > 0, "Empty path?"

        output: Any = None
        for rule in rules:
            inputs = self.subjects.filter(rule.input_types) | params.filter(rule.input_types)
            output = self.executor.execute(rule, inputs, self)
            params = params | Params(output)

        assert isinstance(output, output_type), f"Expected {output_type}, got {type(output)}"
        return output


def get(output_type: type[T], *inputs: object) -> T:
    """
    Delegate to the engine to retrieve the specified output type given the input parameters.
    """

    engine = RulesEngine.current()

    return engine.get(output_type, Params(*inputs))
